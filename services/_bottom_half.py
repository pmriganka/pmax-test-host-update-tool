def execute_command(self, hostname, host, username, password, release, updateadios):

    logging.info(f"Connecting to host {host} ({hostname}) for ready/Adios operations")

    COMMAND_TIMEOUT = 1800
    POLL_DEADLINE = 3600
    READY_POLL_DEADLINE = 3600

    def connect_with_retry(client, target_host, user, pwd, label):
        for attempt in range(1, 4):
            try:
                client.connect(target_host, username=user, password=pwd, timeout=15)
                return
            except Exception as e:
                logging.error(f"{label} connect attempt {attempt} to {target_host} failed: {e}")
                if attempt == 3:
                    raise
                time.sleep(3)

    def wait_for_exit(channel, timeout_sec):
        deadline = time.time() + timeout_sec
        while not channel.exit_status_ready():
            if time.time() > deadline:
                logging.warning(f"Command timed out after {timeout_sec}s on {hostname}")
                return -1
            time.sleep(5)
        return channel.recv_exit_status()

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        connect_with_retry(ssh, host, username, password, "Primary")
    except Exception as e:
        logging.error(f"Skipping host {host} ({hostname}): unable to establish primary SSH connection: {e}")
        return

    sec_ssh = paramiko.SSHClient()
    sec_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        connect_with_retry(sec_ssh, host, username, password, "Secondary")
    except Exception as e:
        logging.error(f"Skipping host {host} ({hostname}): unable to establish secondary SSH connection: {e}")
        ssh.close()
        return

    try:
        stdin, stdout, stderr = ssh.exec_command("axcli state | grep STATE | awk 'NR==1'")
        output = stdout.read().decode()

        if "Running failed; Tests run failed (RUF)" in output:
            stdin, stdout, stderr = ssh.exec_command("axcli reset")
            deadline = time.time() + POLL_DEADLINE
            while time.time() < deadline:
                self._check_stop()
                stdin, stdout, stderr = ssh.exec_command("axcli state | grep STATE | awk 'NR==1'")
                output = stdout.read().decode()
                if "Running failed; Tests run failed (RUF)" not in output:
                    break
                time.sleep(1)

        if "Running" in output:
            stdin, stdout, stderr = ssh.exec_command("axcli kill -9")
            deadline = time.time() + POLL_DEADLINE
            while time.time() < deadline:
                self._check_stop()
                stdin, stdout, stderr = ssh.exec_command("axcli state | grep STATE | awk 'NR==1'")
                output = stdout.read().decode()
                if "Running" not in output:
                    break
                time.sleep(1)

        if "DNR" not in output:
            stdin, stdout, stderr = ssh.exec_command("axcli dexit -all")
            output = stdout.read().decode()
            deadline = time.time() + POLL_DEADLINE
            while time.time() < deadline:
                self._check_stop()
                stdin, stdout, stderr = ssh.exec_command("axcli state | grep STATE | awk 'NR==1'")
                output = stdout.read().decode()
                if "DNR" in output:
                    logging.info(f"Dispatcher set to Not Ready for {hostname}")
                    break
                time.sleep(1)

        time.sleep(20)
        if updateadios == 1:
            logging.info(f"Updating {release} Adios Version for {hostname}")
            stdin, stdout, stderr = ssh.exec_command(f"/usr/adios/axinstall -b {release}")
            exit_status = wait_for_exit(stdout.channel, COMMAND_TIMEOUT)
            if exit_status == 0:
                logging.info(f"Adios has been Updated for host {hostname}")
            else:
                logging.info("Error Occurred : {}".format(exit_status))

        stdin, stdout, stderr = ssh.exec_command("axcli state | grep STATE | awk 'NR==1'")
        output = stdout.read().decode()
        logging.info(f"Configuring Dispatcher for host {hostname}")
        stdin, stdout, stderr = ssh.exec_command("axcli adiosx config")
        exit_status = wait_for_exit(stdout.channel, COMMAND_TIMEOUT)
        if exit_status == 0:
            logging.info(f"Dispatcher configured for host {hostname}. Polling for Final Ready State........")
        else:
            logging.warning(f"axcli adiosx config returned exit status {exit_status} for {hostname}")

        deadline = time.time() + READY_POLL_DEADLINE
        while time.time() < deadline:
            self._check_stop()
            stdin, stdout, stderr = sec_ssh.exec_command("axcli state | grep STATE | awk 'NR==1'")
            output = stdout.read().decode()
            if "Ready" in output:
                logging.info(f"{hostname} is Ready")
                break
            time.sleep(1)
        else:
            logging.warning(f"Timed out waiting for {hostname} to reach Ready state")

    except ScriptStoppedException:
        raise
    except Exception as e:
        logging.error(f"Error during ready/Adios operations on {hostname}: {e}. Skipping host.")
    finally:
        try:
            ssh.close()
        except Exception:
            pass
        try:
            sec_ssh.close()
        except Exception:
            pass

def _check_stop(self):
    if self.stop_event and self.stop_event.is_set():
        logging.info("------------- Script Stopped by User --------------")
        raise ScriptStoppedException("Script stopped by user.")

def main(self, host_management_dict, stop_event=None):

    self.stop_event = stop_event
    found = 0
    vcenter = username = password = None
    boxname = host_management_dict['system'].upper()
    LOG_FOLDER = "Logs"

    if not os.path.exists(LOG_FOLDER):
        os.makedirs(LOG_FOLDER)
        print("Logs folder created.")
    else:
        print("Logs folder already exists. Not creating again.")

    filename='{}_log_{}.log'.format(boxname,datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    # Remove any existing handlers from previous runs
    for h in logger.handlers[:]:
        logger.removeHandler(h)
        h.close()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh = logging.FileHandler(os.path.join(LOG_FOLDER, filename))
    fh.setFormatter(formatter)
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(sh)

    logging.info("------------- Start of Script --------------")
    try:
        self._check_stop()
        for vcenter in self.all_data_centers:

            self.si = self.connect_vcenter(vcenter['vcenter_server'], vcenter['username'], vcenter['password'])
            self.content = self.si.RetrieveContent()

            folder = self.find_folder_by_name(self.content, boxname)

            if folder:
                found = 1
                username = vcenter['username']
                password = vcenter['password']
                vcenter = vcenter['vcenter_server']
                logging.info("Details found in vCenter : " + vcenter)
                matched_hosts, matched_vms = self.get_hosts_and_vms_from_folder(self.content, folder)
                found_content = self.content
                # Deduplicate by name to avoid repeats
                if matched_hosts:
                    host_by_name = {}
                    for h in matched_hosts:
                        if h.name not in host_by_name:
                            host_by_name[h.name] = h
                    matched_hosts = list(host_by_name.values())
                if matched_vms:
                    vm_by_name = {}
                    for vm in matched_vms:
                        if vm.name not in vm_by_name:
                            vm_by_name[vm.name] = vm
                    matched_vms = list(vm_by_name.values())
                break
            else:
                all_details = self.find_vms_with_system_name(self.content, boxname)
                if all_details['hosts'] and all_details['vms']:
                    found = 1
                    username = vcenter['username']
                    password = vcenter['password']
                    vcenter = vcenter['vcenter_server']
                    matched_hosts, matched_vms = all_details['hosts'], all_details['vms']
                    logging.info("Details found in vCenter : " + vcenter)
                    found_content = self.content
                    # Deduplicate by name to avoid repeats
                    if matched_hosts:
                        host_by_name = {}
                        for h in matched_hosts:
                            if h.name not in host_by_name:
                                host_by_name[h.name] = h
                        matched_hosts = list(host_by_name.values())
                    if matched_vms:
                        vm_by_name = {}
                        for vm in matched_vms:
                            if vm.name not in vm_by_name:
                                vm_by_name[vm.name] = vm
                        matched_vms = list(vm_by_name.values())
                else:
                    logging.info("Details Not found in vCenter : " + vcenter['vcenter_server'])

        if found == 1:

            self._check_stop()
            logging.info(" Fetching the details below ............... ")
            logging.info(" List of ESX Hosts for " + boxname + ":")
            for item in matched_hosts:
                logging.info("     " + item.name)
            logging.info(" List of VMs for " + boxname + ":")
            for vm in matched_vms:
                logging.info("     " + vm.name)

            if len(matched_vms) == 0:
                logging.warning("WARNING: No VMs found for " + boxname + ". Cannot proceed with operations.")
                logging.info("------------- End of Script --------------")
                return

            if host_management_dict['esx_reboot'] == "Yes" and host_management_dict['remediate'] == "No":

                matched_vm_with_ips = self.get_vm_ip(matched_vms)
                self._check_stop()
                self.power_off_vms(matched_vms)
                self._check_stop()
                self.enter_maintainence_mode(found_content, matched_hosts)
                self._check_stop()
                self.reboot_host(found_content, matched_hosts)
                self._check_stop()
                self.exit_maintainence_mode(found_content, matched_hosts)
                self._check_stop()
                self.power_on_vms(matched_vms)
                self._check_stop()
                self.wait_for_vm_console_ready(matched_vm_with_ips)
                self._check_stop()
                match_vms_with_cred = self.get_vm_credentials(matched_vm_with_ips)
                if 'script_name' in host_management_dict and 'hostname' in host_management_dict:
                    self.set_up_aclx(match_vms_with_cred, host_management_dict['hostname'], host_management_dict['script_name'])
                if host_management_dict['updateadios'] == "Yes":
                    self.ready_hosts(match_vms_with_cred, host_management_dict.get('adios_versions', ''), 1)
                else:
                    self.ready_hosts(match_vms_with_cred, host_management_dict.get('adios_versions', ''), 0)
                logging.info("------------- End of Script --------------")

            if host_management_dict['vm_reboot'] == "Yes" and host_management_dict['esx_reboot'] == "No " and host_management_dict['remediate'] == "No":

                matched_vm_with_ips = self.get_vm_ip(matched_vms)
                self._check_stop()
                self.power_off_vms(matched_vms)
                self._check_stop()
                time.sleep(60)
                self._check_stop()
                self.power_on_vms(matched_vms)
                self._check_stop()
                self.wait_for_vm_console_ready(matched_vm_with_ips)
                self._check_stop()
                match_vms_with_cred = self.get_vm_credentials(matched_vm_with_ips)
                if 'script_name' in host_management_dict and 'hostname' in host_management_dict:
                    self.set_up_aclx(match_vms_with_cred, host_management_dict['hostname'], host_management_dict['script_name'])
                if host_management_dict['updateadios'] == "Yes":
                    self.ready_hosts(match_vms_with_cred, host_management_dict.get('adios_versions', ''), 1)
                else:
                    self.ready_hosts(match_vms_with_cred, host_management_dict.get('adios_versions', ''), 0)
                logging.info("------------- End of Script --------------")

            if host_management_dict['ready_host'] == "Yes" and host_management_dict['esx_reboot'] == "No" and host_management_dict['vm_reboot'] == "No" and host_management_dict['remediate'] == "No":

                matched_vm_with_ips = self.get_vm_ip(matched_vms)
                self._check_stop()
                match_vms_with_cred = self.get_vm_credentials(matched_vm_with_ips)
                if 'script_name' in host_management_dict and 'hostname' in host_management_dict:
                    self.set_up_aclx(match_vms_with_cred, host_management_dict['hostname'], host_management_dict['script_name'])
                if host_management_dict['updateadios'] == "Yes":
                    self.ready_hosts(match_vms_with_cred, host_management_dict.get('adios_versions', ''), 1)
                else:
                    self.ready_hosts(match_vms_with_cred, host_management_dict.get('adios_versions', ''), 0)
                logging.info("------------- End of Script --------------")

            if host_management_dict['remediate'] == "Yes":

                matched_vm_with_ips = self.get_vm_ip(matched_vms)
                self._check_stop()
                self.power_off_vms(matched_vms)
                self._check_stop()
                self.enter_maintainence_mode(found_content, matched_hosts)
                self._check_stop()
                host_remediation(vcenter, username, password, matched_hosts)
                self._check_stop()
                self.exit_maintainence_mode(found_content, matched_hosts)
                self._check_stop()
                self.power_on_vms(matched_vms)
                self._check_stop()
                self.wait_for_vm_console_ready(matched_vm_with_ips)
                self._check_stop()
                match_vms_with_cred = self.get_vm_credentials(matched_vm_with_ips)
                if 'script_name' in host_management_dict and 'hostname' in host_management_dict:
                    self.set_up_aclx(match_vms_with_cred, host_management_dict['hostname'], host_management_dict['script_name'])
                if host_management_dict['updateadios'] == "Yes":
                    self.ready_hosts(match_vms_with_cred, host_management_dict.get('adios_versions', ''), 1)
                else:
                    self.ready_hosts(match_vms_with_cred, host_management_dict.get('adios_versions', ''), 0)
                logging.info("------------- End of Script --------------")
        else:
            logging.info(" No Details are found . Please verify manually ")

    except ScriptStoppedException:
        logging.error("ERROR: Script aborted by User")
        logging.info("------------- End of Script (Aborted) --------------")
        raise
    except Exception as e:
        logging.error(f"ERROR: Script aborted due to: {str(e)}")
        logging.info("------------- End of Script (Aborted) --------------")
        raise
