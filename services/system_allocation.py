"""
System Allocation service.

Drives an SRP's Physical-Used % up to a user-specified target by:
  1. Discovering VMs of a system via vCenter (reuses HostManagement helpers).
  2. SSH'ing to each VM and enumerating SymDev devices (>10 MB) with symcli.
  3. Reading SRP sizes via `symcfg list -srp -v`.
  4. Resizing TDEVs uniformly if total device size < 1.1 * total SRP size.
  5. Disabling compression on those devices.
  6. Starting raw-device `fio` writes in parallel on every VM.
  7. Polling SRPs; once every SRP's Physical-Used % >= target, runs IO for
     another 5 minutes, kills fio, and exits.
"""

import os
import re
import math
import time
import logging
import threading
from datetime import datetime

import paramiko

from services.host_management import HostManagement, ScriptStoppedException


# ---------- symcli path resolution ----------
SYMCLI_CANDIDATE_DIRS = ["/usr/adios/bin", "/usr/symcli/bin"]


def _remote_run(ssh, cmd, timeout=120):
    """Run a command via paramiko ssh, return (rc, stdout, stderr)."""
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def _ssh_connect(host, user, password, timeout=20):
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(host, username=user, password=password, timeout=timeout)
    tr = cli.get_transport()
    if tr:
        tr.set_keepalive(30)
    return cli


def _resolve_symcli(ssh):
    """Return absolute path to symcli bin dir on this VM, or None."""
    for d in SYMCLI_CANDIDATE_DIRS:
        rc, out, _ = _remote_run(ssh, f"test -x {d}/symcfg && echo ok")
        if rc == 0 and "ok" in out:
            return d
    return None


# ---------- parsers ----------

def parse_symcfg_list_local(text):
    """Parse `symcfg list` output. Returns a list of SID strings (12-digit serials)."""
    sids = []
    for line in text.splitlines():
        # rows look like:  000120001879   Local    8000    PowerMax_2000    ...
        m = re.match(r"\s*(\d{12})\b", line)
        if m:
            sids.append(m.group(1))
    return sids


_SRP_NAME_RE = re.compile(r"^\s*Name\s*:\s*(\S+)\s*$")
_PHYS_CAP_RE = re.compile(r"^\s*Physical Capacity \(GB\)\s*:\s*([\d.]+)")
_PHYS_USED_RE = re.compile(r"^\s*Physical Used Capacity \(GB\)\s*:\s*([\d.]+)")
_DG_TOTAL_RE = re.compile(r"^\s*Total\s+\d+\s+\d+\s+([\d.]+)\s*$")


def parse_srp_verbose(text):
    """
    Parse `symcfg list -srp -v` output into:
      [{name, physical_capacity_gb, physical_used_gb, disk_group_total_gb}, ...]
    """
    srps = []
    cur = None
    in_dg = False
    for line in text.splitlines():
        m = _SRP_NAME_RE.match(line)
        if m and "SRP" in m.group(1).upper():
            if cur:
                srps.append(cur)
            cur = {
                "name": m.group(1),
                "physical_capacity_gb": 0.0,
                "physical_used_gb": 0.0,
                "disk_group_total_gb": 0.0,
            }
            in_dg = False
            continue
        if cur is None:
            continue
        m = _PHYS_CAP_RE.match(line)
        if m:
            cur["physical_capacity_gb"] = float(m.group(1))
            continue
        m = _PHYS_USED_RE.match(line)
        if m:
            cur["physical_used_gb"] = float(m.group(1))
            continue
        if "Disk Groups" in line:
            in_dg = True
            continue
        if in_dg:
            m = _DG_TOTAL_RE.match(line)
            if m:
                cur["disk_group_total_gb"] += float(m.group(1))
                in_dg = False  # only one Total per disk-group block
    if cur:
        srps.append(cur)
    return srps


def parse_sympd_list(text):
    """
    Parse `sympd list` output. Returns list of dicts:
      {pdev: '/dev/sdb', symdev: '00123'}
    """
    rows = []
    for line in text.splitlines():
        # Typical line:
        # /dev/sdb     Not Visible    FA-1D:11   00100  RW    TDEV    ...
        m = re.match(r"\s*(\S?/dev/\S+|\S+)\s+\S+\s+\S+\s+([0-9A-Fa-f]{3,5})\s+", line)
        if m and "/dev/" in m.group(1):
            rows.append({"pdev": m.group(1), "symdev": m.group(2).upper()})
    return rows


_DEV_CAP_MB_RE = re.compile(r"Device Capacity\s*\(Megabytes\)\s*:\s*([\d.]+)")
_DEV_CAP_BLK_RE = re.compile(r"Device Block Capacity\s*\(Blocks\)\s*:\s*(\d+)")


def parse_symdev_show_capacity_mb(text):
    """Extract device capacity in MB from `symdev show` output."""
    m = _DEV_CAP_MB_RE.search(text)
    if m:
        return float(m.group(1))
    m = _DEV_CAP_BLK_RE.search(text)
    if m:
        return float(m.group(1)) * 512 / (1024 * 1024)
    return None


# ---------- main class ----------

class SystemAllocation:
    def __init__(self):
        self.stop_event = None
        self.hm = HostManagement()  # reuse vCenter helpers

    def _check_stop(self):
        if self.stop_event and self.stop_event.is_set():
            logging.info("------------- Script Stopped by User --------------")
            raise ScriptStoppedException("Script stopped by user.")

    # ---------- VM discovery (mirrors host_management.main) ----------
    def _discover_vms(self, boxname):
        from pyVmomi import vim  # local import
        found = 0
        matched_hosts = matched_vms = None
        for vc in self.hm.all_data_centers:
            self.hm.si = self.hm.connect_vcenter(vc['vcenter_server'], vc['username'], vc['password'])
            self.hm.content = self.hm.si.RetrieveContent()
            folder = self.hm.find_folder_by_name(self.hm.content, boxname)
            if folder:
                matched_hosts, matched_vms = self.hm.get_hosts_and_vms_from_folder(self.hm.content, folder)
                logging.info(f"Details found in vCenter : {vc['vcenter_server']}")
                found = 1
                break
            all_details = self.hm.find_vms_with_system_name(self.hm.content, boxname)
            if all_details['hosts'] and all_details['vms']:
                matched_hosts, matched_vms = all_details['hosts'], all_details['vms']
                logging.info(f"Details found in vCenter : {vc['vcenter_server']}")
                found = 1
                break
            logging.info(f"Details Not found in vCenter : {vc['vcenter_server']}")
        if not found:
            return None, None
        # dedupe by name
        _uh = {}
        for h in matched_hosts:
            if h.name not in _uh or isinstance(h, vim.HostSystem):
                _uh[h.name] = h
        matched_hosts = list(_uh.values())
        _uv = {}
        for v in matched_vms:
            if v.name not in _uv:
                _uv[v.name] = v
        matched_vms = list(_uv.values())
        return matched_hosts, matched_vms

    # ---------- SID resolution ----------
    def _resolve_sid(self, ssh, symcli_dir, boxname):
        rc, out, err = _remote_run(ssh, f"{symcli_dir}/symcfg list")
        if rc != 0:
            logging.error(f"🔴 symcfg list failed: {err.strip()}")
            return None
        sids = parse_symcfg_list_local(out)
        if not sids:
            logging.error("🔴 No Symmetrix SIDs returned by symcfg list")
            return None
        if len(sids) == 1:
            return sids[0]
        # try to match the box name suffix to the trailing digits of the SID
        box_digits = re.sub(r"\D", "", boxname)
        for sid in sids:
            if box_digits and box_digits[-4:] in sid:
                logging.info(f"Matched SID {sid} for box {boxname}")
                return sid
        logging.error(f"🔴 Multiple SIDs visible ({sids}); cannot disambiguate for box {boxname}")
        return None

    # ---------- SRP fetch ----------
    def _fetch_srps(self, ssh, symcli_dir, sid):
        rc, out, err = _remote_run(ssh, f"{symcli_dir}/symcfg list -srp -v -sid {sid}", timeout=180)
        if rc != 0:
            logging.error(f"🔴 symcfg list -srp -v failed: {err.strip()}")
            return None, out
        srps = parse_srp_verbose(out)
        if not srps:
            logging.error("🔴 Failed to parse any SRPs from symcfg output")
            return None, out
        for s in srps:
            logging.info(
                f"  SRP {s['name']}: phys_cap={s['physical_capacity_gb']} GB, "
                f"used={s['physical_used_gb']} GB, dg_total={s['disk_group_total_gb']} GB"
            )
        return srps, out

    # ---------- device enumeration per VM ----------
    def _list_vm_devices(self, ssh, symcli_dir, sid):
        rc, out, err = _remote_run(ssh, f"{symcli_dir}/sympd list -sid {sid}", timeout=120)
        if rc != 0:
            logging.error(f"🔴 sympd list failed: {err.strip()}")
            return []
        rows = parse_sympd_list(out)
        devs = []
        for row in rows:
            self._check_stop()
            rc, dout, _ = _remote_run(
                ssh, f"{symcli_dir}/symdev show {row['symdev']} -sid {sid}", timeout=60
            )
            if rc != 0:
                continue
            mb = parse_symdev_show_capacity_mb(dout)
            if mb is None or mb <= 10:
                continue
            devs.append({"symdev": row['symdev'], "pdev": row['pdev'], "size_mb": mb})
        return devs

    # ---------- resize ----------
    def _group_contiguous(self, symdev_hex_list):
        """Group hex devids into contiguous ranges."""
        if not symdev_hex_list:
            return []
        ints = sorted({int(d, 16) for d in symdev_hex_list})
        ranges = []
        s = p = ints[0]
        for n in ints[1:]:
            if n == p + 1:
                p = n
            else:
                ranges.append((s, p))
                s = p = n
        ranges.append((s, p))
        # convert back to hex with same width as input
        width = max(len(d) for d in symdev_hex_list)
        return [(format(a, f"0{width}X"), format(b, f"0{width}X")) for a, b in ranges]

    def _resize_devices(self, vm_dev_map, sid, new_size_gb):
        for vm, info in vm_dev_map.items():
            self._check_stop()
            ssh = info['ssh']
            symcli_dir = info['symcli_dir']
            devs = info['devices']
            if not devs:
                continue
            ranges = self._group_contiguous([d['symdev'] for d in devs])
            for lo, hi in ranges:
                cmd = (
                    f"{symcli_dir}/symdev -sid {sid} modify -tdev -cap {new_size_gb} "
                    f"-captype gb -devs {lo}:{hi} -nop"
                )
                logging.info(f"[{vm}] {cmd}")
                rc, out, err = _remote_run(ssh, cmd, timeout=600)
                if rc != 0:
                    logging.error(f"🔴 [{vm}] resize {lo}:{hi} failed: {err.strip() or out.strip()}")
                else:
                    logging.info(f"🟢 [{vm}] resize {lo}:{hi} OK")
            # symcfg discover after resize
            _remote_run(ssh, f"{symcli_dir}/symcfg discover", timeout=300)
            # host-side rescan
            _remote_run(ssh, "for d in /sys/class/block/sd*/device/rescan; do echo 1 > $d; done")
            _remote_run(ssh, "command -v multipath >/dev/null && multipath -r || true")

    # ---------- disable compression ----------
    def _disable_compression(self, vm_dev_map, sid):
        for vm, info in vm_dev_map.items():
            self._check_stop()
            ssh = info['ssh']
            symcli_dir = info['symcli_dir']
            devs = info['devices']
            if not devs:
                continue
            ranges = self._group_contiguous([d['symdev'] for d in devs])
            for lo, hi in ranges:
                cmd = (
                    f"{symcli_dir}/symdev -sid {sid} modify -nocompression "
                    f"-devs {lo}:{hi} -nop"
                )
                logging.info(f"[{vm}] {cmd}")
                rc, out, err = _remote_run(ssh, cmd, timeout=300)
                if rc != 0:
                    logging.warning(f"🟡 [{vm}] disable-compression {lo}:{hi}: {err.strip() or out.strip()}")
                else:
                    logging.info(f"🟢 [{vm}] disable-compression {lo}:{hi} OK")

    # ---------- fio launch ----------
    def _ensure_fio(self, ssh, vm_name):
        rc, out, _ = _remote_run(ssh, "command -v fio")
        if rc == 0 and out.strip():
            return out.strip()
        logging.info(f"[{vm_name}] fio not present; attempting install")
        for installer in ("yum install -y fio", "dnf install -y fio", "apt-get install -y fio"):
            rc, _, _ = _remote_run(ssh, installer, timeout=600)
            if rc == 0:
                rc2, out2, _ = _remote_run(ssh, "command -v fio")
                if rc2 == 0 and out2.strip():
                    return out2.strip()
        return None

    def _start_fio_on_vm(self, vm_name, info, results):
        ssh = info['ssh']
        devs = info['devices']
        try:
            fio_bin = self._ensure_fio(ssh, vm_name)
            if not fio_bin:
                results[vm_name] = {"ok": False, "err": "fio unavailable"}
                return
            if not devs:
                results[vm_name] = {"ok": True, "pid": None, "note": "no devices"}
                return
            # build jobfile
            lines = [
                "[global]",
                "ioengine=libaio",
                "direct=1",
                "bs=1M",
                "rw=write",
                "numjobs=1",
                "iodepth=32",
                "group_reporting=1",
                "time_based=0",
                "size=100%",
                "",
            ]
            for d in devs:
                lines.append(f"[job-{d['symdev']}]")
                lines.append(f"filename={d['pdev']}")
                lines.append("")
            jobfile = "/tmp/sysalloc.fio"
            here = "\n".join(lines).replace("'", "'\\''")
            _remote_run(ssh, f"cat > {jobfile} <<'EOF'\n{here}\nEOF")
            launch = (
                f"nohup {fio_bin} {jobfile} > /tmp/sysalloc.fio.log 2>&1 & echo $!"
            )
            rc, out, err = _remote_run(ssh, launch, timeout=30)
            pid = out.strip().splitlines()[-1] if out.strip() else None
            if rc == 0 and pid and pid.isdigit():
                logging.info(f"🟢 [{vm_name}] fio started PID {pid}")
                results[vm_name] = {"ok": True, "pid": pid}
            else:
                logging.error(f"🔴 [{vm_name}] fio launch failed: {err or out}")
                results[vm_name] = {"ok": False, "err": err or out}
        except Exception as e:
            logging.error(f"🔴 [{vm_name}] fio exception: {e}")
            results[vm_name] = {"ok": False, "err": str(e)}

    def _start_fio_all(self, vm_dev_map):
        threads = []
        results = {}
        for vm, info in vm_dev_map.items():
            t = threading.Thread(target=self._start_fio_on_vm, args=(vm, info, results), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        return results

    def _stop_fio_all(self, vm_dev_map, fio_results):
        for vm, info in vm_dev_map.items():
            ssh = info['ssh']
            pid = (fio_results.get(vm) or {}).get('pid')
            try:
                if pid:
                    _remote_run(ssh, f"kill -9 {pid} 2>/dev/null || true")
                _remote_run(ssh, "pkill -9 fio 2>/dev/null || true")
                logging.info(f"🟢 [{vm}] fio stopped")
            except Exception as e:
                logging.warning(f"🟡 [{vm}] fio stop error: {e}")

    # ---------- monitor loop ----------
    def _monitor(self, ssh, symcli_dir, sid, target_pct):
        while True:
            self._check_stop()
            srps, _ = self._fetch_srps(ssh, symcli_dir, sid)
            if not srps:
                time.sleep(30)
                continue
            all_met = True
            for s in srps:
                cap = s['physical_capacity_gb'] or 1.0
                used_pct = (s['physical_used_gb'] / cap) * 100.0
                logging.info(f"  [{s['name']}] used={s['physical_used_gb']} GB / cap={cap} GB = {used_pct:.2f}% (target {target_pct}%)")
                if used_pct < target_pct:
                    all_met = False
            if all_met:
                logging.info(f"🟢 All SRPs reached target {target_pct}%")
                return True
            for _ in range(30):
                self._check_stop()
                time.sleep(1)

    # ---------- main ----------
    def main(self, params, stop_event=None):
        self.stop_event = stop_event
        boxname = params['system'].upper()
        target_pct = float(params['percentage'])

        LOG_FOLDER = "Logs"
        if not os.path.exists(LOG_FOLDER):
            os.makedirs(LOG_FOLDER)
        filename = f"OGSCK_system_allocation_log_{boxname}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
        fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh = logging.FileHandler(os.path.join(LOG_FOLDER, filename))
        fh.setFormatter(fmt)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(sh)

        logging.info("------------- Start of Script --------------")
        logging.info(f"Box: {boxname}  Target %: {target_pct}")
        vm_dev_map = {}  # vm_name -> {ssh, symcli_dir, devices, ip}
        fio_results = {}
        try:
            self._check_stop()
            matched_hosts, matched_vms = self._discover_vms(boxname)
            if not matched_vms:
                logging.info(" No Details are found . Please verify manually ")
                logging.info("------------- End of Script --------------")
                return

            logging.info(" List of VMs for " + boxname + ":")
            for vm in matched_vms:
                logging.info("     " + vm.name)

            vm_with_ips = self.hm.get_vm_ip(matched_vms)
            self._check_stop()
            vm_creds = self.hm.get_vm_credentials(vm_with_ips)
            valid = [v for v in vm_creds if v.get('hostip') and v.get('username') and v.get('password')]
            if not valid:
                logging.error("🔴 No VMs with valid credentials. Aborting.")
                logging.info("------------- End of Script --------------")
                return

            # connect SSH to each valid VM
            for v in valid:
                self._check_stop()
                try:
                    ssh = _ssh_connect(v['hostip'], v['username'], v['password'])
                    symcli_dir = _resolve_symcli(ssh)
                    if not symcli_dir:
                        logging.warning(f"🟡 symcli not found on {v['hostname']}; skipping")
                        ssh.close()
                        continue
                    vm_dev_map[v['hostname']] = {
                        "ssh": ssh,
                        "symcli_dir": symcli_dir,
                        "devices": [],
                        "ip": v['hostip'],
                    }
                except Exception as e:
                    logging.warning(f"🟡 SSH to {v['hostname']} failed: {e}")

            if not vm_dev_map:
                logging.error("🔴 No VMs reachable with symcli. Aborting.")
                logging.info("------------- End of Script --------------")
                return

            # SID from first VM
            first_vm = next(iter(vm_dev_map))
            first_info = vm_dev_map[first_vm]
            sid = self._resolve_sid(first_info['ssh'], first_info['symcli_dir'], boxname)
            if not sid:
                logging.info("------------- End of Script --------------")
                return
            logging.info(f"🟢 Using SID {sid}")

            # SRP capacities
            self._check_stop()
            logging.info("------------- Fetching SRP info --------------")
            srps, _ = self._fetch_srps(first_info['ssh'], first_info['symcli_dir'], sid)
            if not srps:
                logging.info("------------- End of Script --------------")
                return
            total_srp_gb = sum(s['disk_group_total_gb'] for s in srps)
            logging.info(f"🟢 Total SRP capacity (disk-group totals): {total_srp_gb} GB")

            # device enumeration per VM
            self._check_stop()
            logging.info("------------- Enumerating devices per VM --------------")
            total_dev_mb = 0.0
            for vm, info in vm_dev_map.items():
                self._check_stop()
                devs = self._list_vm_devices(info['ssh'], info['symcli_dir'], sid)
                info['devices'] = devs
                sub = sum(d['size_mb'] for d in devs)
                total_dev_mb += sub
                logging.info(f"  [{vm}] {len(devs)} devices >10MB, total={sub/1024:.2f} GB")
                for d in devs:
                    logging.info(f"     {d['symdev']}  {d['pdev']}  {d['size_mb']:.1f} MB")
            total_dev_gb = total_dev_mb / 1024.0
            logging.info(f"🟢 Total device size across VMs: {total_dev_gb:.2f} GB")

            # resize if needed
            target_total_gb = 1.1 * total_srp_gb
            if total_dev_gb < target_total_gb:
                deficit_gb = math.ceil(target_total_gb - total_dev_gb)
                dev_count = sum(len(i['devices']) for i in vm_dev_map.values())
                if dev_count == 0:
                    logging.error("🔴 No devices to resize. Aborting.")
                    logging.info("------------- End of Script --------------")
                    return
                bump_per_dev_gb = math.ceil(deficit_gb / dev_count)
                # uniform new size: max current + bump (use ceiling of largest current dev)
                max_current_gb = max(
                    (d['size_mb'] / 1024.0) for i in vm_dev_map.values() for d in i['devices']
                )
                new_size_gb = int(math.ceil(max_current_gb + bump_per_dev_gb))
                logging.info(
                    f"🟢 Need to grow: deficit={deficit_gb} GB across {dev_count} devices "
                    f"-> new uniform size = {new_size_gb} GB per device"
                )
                self._check_stop()
                logging.info("------------- Resizing devices --------------")
                self._resize_devices(vm_dev_map, sid, new_size_gb)
                # re-enumerate to confirm
                logging.info("------------- Verifying new device sizes --------------")
                for vm, info in vm_dev_map.items():
                    info['devices'] = self._list_vm_devices(info['ssh'], info['symcli_dir'], sid)
                    sub = sum(d['size_mb'] for d in info['devices']) / 1024.0
                    logging.info(f"  [{vm}] post-resize total = {sub:.2f} GB")
            else:
                logging.info(
                    f"🟢 Existing devices already exceed 1.1*SRP ({total_dev_gb:.2f} >= {target_total_gb:.2f} GB); "
                    "skipping resize"
                )

            # disable compression
            self._check_stop()
            logging.info("------------- Disabling compression --------------")
            self._disable_compression(vm_dev_map, sid)

            # start fio
            self._check_stop()
            logging.info("------------- Starting fio writes --------------")
            fio_results = self._start_fio_all(vm_dev_map)

            # monitor
            self._check_stop()
            logging.info("------------- Monitoring SRP allocation --------------")
            self._monitor(first_info['ssh'], first_info['symcli_dir'], sid, target_pct)

            # 5 more minutes of IO
            logging.info("🟢 Target reached. Continuing IO for 5 more minutes ...")
            end = time.time() + 300
            while time.time() < end:
                self._check_stop()
                time.sleep(5)

            logging.info("------------- Stopping fio --------------")
            self._stop_fio_all(vm_dev_map, fio_results)

            # final report
            srps, _ = self._fetch_srps(first_info['ssh'], first_info['symcli_dir'], sid)
            if srps:
                logging.info("Final SRP state:")
                for s in srps:
                    cap = s['physical_capacity_gb'] or 1.0
                    logging.info(
                        f"  [{s['name']}] used={s['physical_used_gb']} GB / cap={cap} GB "
                        f"= {(s['physical_used_gb']/cap)*100:.2f}%"
                    )

            logging.info("------------- End of Script --------------")

        except ScriptStoppedException:
            logging.error("ERROR: Script aborted by User")
            try:
                self._stop_fio_all(vm_dev_map, fio_results)
            except Exception:
                pass
            logging.info("------------- End of Script (Aborted) --------------")
            raise
        except Exception as e:
            logging.error(f"ERROR: Script aborted due to: {e}")
            try:
                self._stop_fio_all(vm_dev_map, fio_results)
            except Exception:
                pass
            logging.info("------------- End of Script (Aborted) --------------")
            raise
        finally:
            for vm, info in vm_dev_map.items():
                try:
                    info['ssh'].close()
                except Exception:
                    pass
