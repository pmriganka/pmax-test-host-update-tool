
import os
import json
import random
from dotenv import load_dotenv
from datetime import datetime
from pyVmomi import vim
import logging
import time
import paramiko
import itertools
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
import ssl
import subprocess
import tempfile
import socket
import atexit
import threading
from services.host_remediation import host_remediation


load_dotenv()


class ScriptStoppedException(Exception):
    """Raised when the user stops the script from the UI."""
    pass


class HostManagement:
    def __init__(self):
        self.stop_event = None
        self.all_data_centers = [
            {
                "vcenter_server" : f"{os.getenv('vcenter_est_hop_server')}",
                "username" : f"{os.getenv('vcenter_est_hop_username')}",
                "password" : f"{os.getenv('vcenter_est_hop_password')}"
            },{
                "vcenter_server" : f"{os.getenv('vcenter_be_hop_server')}",
                "username" : f"{os.getenv('vcenter_be_hop_username')}",
                "password" : f"{os.getenv('vcenter_be_hop_password')}"
            },{
                "vcenter_server" : f"{os.getenv('vcenter_est_be_cork_server')}",
                "username" : f"{os.getenv('vcenter_est_be_cork_username')}",
                "password" : f"{os.getenv('vcenter_est_be_cork_password')}"
            }]
        self.si = None
        self.content = None


    def connect_vcenter (self, vcenter , username, password ):
        context = ssl._create_unverified_context()
        si = SmartConnect(host=vcenter, user=username, pwd=password, sslContext=context)
        atexit.register(Disconnect, si)
        return si

    def get_container_view(self, content, container):

        vimTypes = [ vim.Folder, vim.VirtualMachine, vim.ComputeResource, vim.HostSystem ]
        view = content.viewManager.CreateContainerView(container, vimTypes, True)
        objs = list(view.view)
        view.Destroy()
        return objs

    def find_folder_by_name(self, content, system_name):

        container = self.get_container_view(content, content.rootFolder)
        for item in container:
            if system_name in item.name and isinstance(item, vim.Folder):
                # Check if this is a datastore folder (which we don't want)
                if hasattr(item, 'parent') and item.parent:
                    parent_name = getattr(item.parent, 'name', '').lower()
                    if 'datastore' in parent_name or 'storage' in parent_name:
                        continue
                
                return item
        
        return None

    def get_hosts_and_vms_from_folder(self, content, folder):

        hosts = set()
        vms = set()

        # Get container view of folder contents
        entity = self.get_container_view(content, folder)
        
        for child in entity:
            if isinstance(child, vim.ComputeResource):
                hosts.add(child)
                
                # Get VMs from this compute resource
                if hasattr(child, 'resourcePool') and child.resourcePool:
                    if hasattr(child.resourcePool, 'vm') and child.resourcePool.vm:
                        for vm in child.resourcePool.vm:
                            vms.add(vm)
                    
            elif isinstance(child, vim.HostSystem):
                hosts.add(child)
                
                # Try to get VMs from this host
                if hasattr(child, 'vm') and child.vm:
                    for vm in child.vm:
                        vms.add(vm)
                        
            elif isinstance(child, vim.VirtualMachine):
                vms.add(child)
            
            elif isinstance(child, vim.Folder):
                # Recursively search subfolders
                sub_hosts, sub_vms = self.get_hosts_and_vms_from_folder(content, child)
                hosts.update(sub_hosts)
                vms.update(sub_vms)
        
        return hosts, vms
    
    def find_vms_with_system_name(self, content, system_name):

        hosts = set()
        vms = set()
        all_details = {}

        vm_detected = 0
        entity = self.get_container_view(content, content.rootFolder)
        for item in entity:
            
            if isinstance(item, vim.Folder):
                continue

            if isinstance(item, vim.ComputeResource):       
                for vm in item.resourcePool.vm:
                    if system_name in vm.name:
        
                        hosts.add(item)
        
        for host in hosts:  
            for vm in host.resourcePool.vm:
                vms.add(vm)
                    
        
        all_details['hosts'] = hosts
        all_details['vms'] = vms
        return all_details
    
    def get_vm_ip(self, vms):

        logging.info("------------- Fetching the VM IPs --------------")

        # If any VMs are powered off, power them on first so we can fetch their IPs
        off_vms = [vm for vm in vms if vm.runtime.powerState != vim.VirtualMachinePowerState.poweredOn]
        if off_vms:
            logging.info(f" {len(off_vms)} VM(s) are not powered on. Powering them on to fetch IPs...")
            self.power_on_vms(off_vms)

        logging.info(" Fetching the VM IPs ....")
        vm_details = []
        ip_wait_deadline = 300  # seconds per VM to wait for an IP after power-on

        for vm in vms:
            ip = None
            try:
                ip = vm.guest.ipAddress
            except Exception:
                ip = None

            # If the VM was just powered on, give it time to report an IP via VMware Tools
            if ip is None and vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
                end_time = time.time() + ip_wait_deadline
                while time.time() < end_time:
                    self._check_stop()
                    try:
                        ip = vm.guest.ipAddress
                    except Exception:
                        ip = None
                    if ip:
                        break
                    time.sleep(10)

            logging.info(f"     {vm.name} -> {ip}")
            vm_details.append({"vm": vm, "vm_ip": ip})

        return vm_details

    def _power_off_single_vm(self, vm):
        try:
            if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOff:
                logging.info(f"{vm.name} is already powered off.")
                return
            logging.info(f" Powering off {vm.name} (hard)...")
            task = vm.PowerOffVM_Task()
            while task.info.state in [vim.TaskInfo.State.running, vim.TaskInfo.State.queued]:
                self._check_stop()
                time.sleep(5)
            if task.info.state == vim.TaskInfo.State.success:
                logging.info(f"{vm.name} powered off.")
            else:
                logging.error(f"Failed to power off {vm.name}: {task.info.error}")
        except ScriptStoppedException:
            raise
        except Exception as e:
            logging.error(f"Error powering off {vm.name}: {e}")

    def power_off_vms( self, vms ):

        logging.info("------------- Powering Off the VMs --------------")
        threads = []
        for vm in vms:
            t = threading.Thread(target=self._power_off_single_vm, args=(vm,))
            t.daemon = True
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
         
    def enter_maintainence_mode( self, content, hosts ):
        
        logging.info("------------- Entering Maintainence Mode --------------")
        container = content.viewManager.CreateContainerView(content.rootFolder, [vim.HostSystem], True)

        for host in hosts: 
            for child in container.view:
                if host.name in child.name:
                    if not child.runtime.inMaintenanceMode:
                        task = child.EnterMaintenanceMode_Task(timeout=300, evacuatePoweredOffVms=False)
                        while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
                            self._check_stop()
                            logging.info( "Waiting.....", task.info.progress )
                            time.sleep(5)
                        if task.info.state == vim.TaskInfo.State.success:
                            logging.info(f"Host {host.name} in maintenance mode")
                        else:
                            logging.error(f"Failed to enter maintenance mode on host: {task.info.error}")
                    else:
                        logging.info(f"The host {host.name} is already in maintenance mode")

        container.Destroy()

    def reboot_host(self, content, hosts):
        """
        Reboots an ESX host and waits for it to get connected again.
        
        Parameters:
        host_name (str): The name of the ESX host to reboot.
        vsphere_client: The vSphere client object.
        
        Returns:
        None
        """

        logging.info("------------- Rebooting the Hosts --------------")
        container = content.viewManager.CreateContainerView(content.rootFolder, [vim.HostSystem], True)

        for host in hosts: 
            for child in container.view:
                if host.name in child.name:
                    
                    logging.info(f"Initiating reboot for host: {host.name}")
                    task = child.RebootHost_Task(force=True)
                    
                    disconnect_deadline = time.time() + 1800
                    while time.time() < disconnect_deadline:
                        self._check_stop()
                        cs = child.summary.runtime.connectionState
                        ps = child.summary.runtime.powerState
                        logging.info(f"[WaitUp] connectionState={cs}, powerState={ps}")
                        if str(cs).lower() == "notresponding":
                            break
                        time.sleep(10)
                    
                    reconnect_deadline = time.time() + 1800
                    while time.time() < reconnect_deadline:
                        self._check_stop()
                        try:
                            cs = child.summary.runtime.connectionState
                            ps = child.summary.runtime.powerState
                            logging.info(f"[WaitUp] connectionState={cs}, powerState={ps}")
                            if str(cs).lower() == "connected":
                                logging.info(f"Host {host.name} is connected")
                                break
                        except Exception as e:
                            logging.error("Exception occured: " + str(e))
                        time.sleep(10)
                    
        container.Destroy()
    def exit_maintainence_mode( self, content, hosts ):
        
        logging.info("------------- Exiting Maintainence Mode --------------")
        container = content.viewManager.CreateContainerView(content.rootFolder, [vim.HostSystem], True)

        for host in hosts: 
            for child in container.view:
                if host.name in child.name:
                    if child.runtime.inMaintenanceMode:
                        task = child.ExitMaintenanceMode_Task(timeout=300)
                        while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
                            self._check_stop()
                            logging.info( "Waiting.....", task.info.progress )
                            time.sleep(5)
                        if task.info.state == vim.TaskInfo.State.success:
                            logging.info(f"Host {host.name} is Not in maintenance mode")
                        else:
                            logging.error(f"Failed to exit maintenance mode on host: {task.info.error}")
                    else:
                        logging.info(f"The host {host.name} is already Not in maintenance mode")

        container.Destroy()

    def _power_on_single_vm(self, vm):
        try:
            if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
                logging.info(f" {vm.name} is already powered on.")
                return
            logging.info(f" Powering on {vm.name}...")
            task = vm.PowerOnVM_Task()
            while task.info.state in [vim.TaskInfo.State.running, vim.TaskInfo.State.queued]:
                self._check_stop()
                time.sleep(5)
            if task.info.state == vim.TaskInfo.State.success:
                logging.info(f"{vm.name} powered on.")
            else:
                logging.error(f"Failed to power on {vm.name}: {task.info.error}")
        except ScriptStoppedException:
            raise
        except Exception as e:
            logging.error(f"Error powering on {vm.name}: {e}")

    def power_on_vms( self, vms ):

        logging.info("------------- Powering on the VMs  --------------")
        threads = []
        for vm in vms:
            t = threading.Thread(target=self._power_on_single_vm, args=(vm,))
            t.daemon = True
            t.start()
            threads.append(t)
        for t in threads:
            t.join()      
    def wait_for_vm_console_ready(self, vm_details):
        
        logging.info("------------- Waiting for the console to be Ready  --------------")
        logging.info("Waiting for the consoles to come up....")
        for item in vm_details:
           
            host_obj = item['vm']
            host_name = host_obj.name
            ping_count_param = "-n" if os.name == "nt" else "-c"

            end_time = time.time() + 4000
            
            if item['vm_ip'] is not None:
                while time.time() < end_time:
                    self._check_stop()
                    try:
                        result = subprocess.run(["ping", ping_count_param, "1", item['vm_ip']], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if result.returncode == 0:
                            logging.info(f"VM {host_name} is ready")
                            break
                    except:
                        logging.info(f"VM {host_name} is Not Yet ready")            
                    time.sleep(10)
            else:
                logging.info(f" Ip not available for host {host_name}")         
    def get_vm_credentials(self, vm_details):

        logging.info("------------- Fetching the correct credentials for the VMs  --------------")
        logging.info(" Fetching the credentials for the VMs .....")
        
        vm_details_with_login = []
        username = "root"
        passwords = ['dangerous', 'D@ngerous', 'D@nger0us1']
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        for item in vm_details:
            
            host_ip = item['vm_ip']
            host_obj = item['vm']
            host_name = host_obj.name
            new_entry = {}
            
            if item['vm_ip'] is not None:
                credentials_found = False
                for password in passwords:
                    ssh = paramiko.SSHClient()  # Create a new SSHClient object
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                    try:
                        ssh.connect(host_ip, username=username, password=password, timeout=10)
                        new_entry['hostname'] = host_name
                        new_entry['hostip'] = host_ip
                        new_entry['username'] = username
                        new_entry['password'] = password
                        vm_details_with_login.append(new_entry)
                        logging.info(f"Credentials found for {host_name} : {username} : {password}")
                        credentials_found = True
                        break
                    except paramiko.ssh_exception.AuthenticationException:
                        continue
                    except (paramiko.SSHException, OSError, Exception) as e:
                        logging.warning(f"Cannot connect to {host_name} ({host_ip}): {str(e)}")
                        break  # Stop trying other passwords if connection fails
                    finally:
                        ssh.close()  # Close the SSHClient object
                
                if not credentials_found:
                    # Add entry with no credentials if we couldn't connect or authenticate
                    new_entry['hostname'] = host_name
                    new_entry['hostip'] = host_ip
                    new_entry['username'] = None
                    new_entry['password'] = None
                    vm_details_with_login.append(new_entry)
                    logging.warning(f"No credentials found for {host_name} ({host_ip})")
            else:
                new_entry['hostname'] = host_name
                new_entry['hostip'] = host_ip
                new_entry['username'] = None
                new_entry['password'] = None
                vm_details_with_login.append(new_entry)
                logging.info(f"No IP available for {host_name}")

        return vm_details_with_login

    def set_up_aclx(self, vm_details_with_login, hostname, script_name):
        
        logging.info("------------- Configuring ACLX DB for the system --------------")
        hostname = hostname.lower()
        hostip = username = password = None
        exit_status = 0
        
        # Try to find the VM by matching hostname
        for item in vm_details_with_login:
            vm_name = item['hostname'].lower()
            # Check if the provided hostname matches the VM name or is contained in it
            if hostname in vm_name or vm_name in hostname:
                hostip = item['hostip']
                username = item['username']
                password = item['password']
                logging.info(f"Found matching VM: {item['hostname']} with IP: {hostip}")
                break
        
        # If no match found by name, use the first VM with valid credentials
        if hostip is None:
            for item in vm_details_with_login:
                if item['hostip'] and item['username'] and item['password']:
                    hostip = item['hostip']
                    username = item['username']
                    password = item['password']
                    logging.warning(f"No VM matched hostname '{hostname}', using first available VM: {item['hostname']} ({hostip})")
                    break
        
        # Check if we have valid connection details
        if not hostip or not username or not password:
            logging.error(f"Cannot configure ACLX: No valid VM found for hostname '{hostname}' or no VMs have valid credentials")
            return
            
        try:
            client = paramiko.client.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            logging.info(f"Connecting to {hostip} as {username} for ACLX configuration...")
            client.connect(hostip, username=username, password=password)
            
            logging.info("Starting the aclx restore script.....")
            stdin,stdout,stderr = client.exec_command(f"chmod 777 {script_name}")
            logging.info("Permissions changed")
            exit_status = stdout.channel.recv_exit_status()
            time.sleep(10)
            if script_name.endswith('.py'):
                _stdin,_stdout,_stderr = client.exec_command(f"python3 {script_name}")
                logging.info("Python aclx db script initiated")
                output = _stdout.read().decode()
                error = _stderr.read().decode()
                exit_status = _stdout.channel.recv_exit_status()
            else:
                _stdin,_stdout,_stderr = client.exec_command(f"{script_name}")
                logging.info("Shell aclx db script initiated")
                output = _stdout.read().decode()
                error = _stderr.read().decode()
                exit_status = _stdout.channel.recv_exit_status()                    
            if exit_status == 0:
                logging.info(f"Aclx DB file restore is successful for host {hostname}")
        except Exception as e:
            logging.error(f"Error Occurred during aclx db restore : {e}")
        finally:
            client.close()
    
    def safe_exec_command(self, ssh_client, command, timeout=None, get_pty=False):
        """Safely execute SSH command with error handling."""
        try:
            stdin, stdout, stderr = ssh_client.exec_command(command, timeout=timeout, get_pty=get_pty)
            return stdin, stdout, stderr, None
        except socket.timeout:
            return None, None, None, "timeout"
        except (paramiko.SSHException, OSError) as e:
            return None, None, None, f"ssh_error: {str(e)}"
        except Exception as e:
            return None, None, None, f"error: {str(e)}"
    
    def execute_command(self, hostname,  host, username, password, release, updateadios):

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=username, password=password)
        
        # Set keepalive to prevent timeout
        transport = ssh.get_transport()
        transport.set_keepalive(30)  # Send keepalive every 30 seconds

        sec_ssh = paramiko.SSHClient()
        sec_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        sec_ssh.connect(host, username=username, password=password)
        
        # Set keepalive for second connection too
        sec_transport = sec_ssh.get_transport()
        sec_transport.set_keepalive(30)

        # Issue "axcli state" command
        stdin, stdout, stderr = ssh.exec_command("axcli state | grep STATE | awk 'NR==1'")
        output = stdout.read().decode()
        
        if "Running failed; Tests run failed (RUF)" in output:
            # Issue "kill -9" command
            stdin, stdout, stderr = ssh.exec_command("axcli reset")

            # Poll for output to not contain "Running"
            while True:
                self._check_stop()
                stdin, stdout, stderr = ssh.exec_command("axcli state | grep STATE | awk 'NR==1'")
                output = stdout.read().decode()
                if "Running failed; Tests run failed (RUF)" not in output:
                    break
                time.sleep(1)

        # Check if output contains "Running"
        if "Running" in output:
            # Issue "kill -9" command
            stdin, stdout, stderr = ssh.exec_command("axcli kill -9")

            # Poll for output to not contain "Running"
            while True:
                self._check_stop()
                stdin, stdout, stderr = ssh.exec_command("axcli state | grep STATE | awk 'NR==1'")
                output = stdout.read().decode()
                if "Running" not in output:
                    break
                time.sleep(1)

        if "DNR" not in output:
            stdin, stdout, stderr = ssh.exec_command("axcli dexit -all")
            output = stdout.read().decode()
            while True:
                self._check_stop()
                stdin, stdout, stderr = ssh.exec_command("axcli state | grep STATE | awk 'NR==1'")
                output = stdout.read().decode()
                if "DNR" in output:
                    logging.info(f"Dispatcher set to Not Ready for {hostname}")
                    break
                time.sleep(1)
        
        time.sleep(20)
        if updateadios == 1 and release is not None and release != "":
            try:
                logging.info(f"Updating {release} Adios Version for {hostname}")
                # Use get_pty=True to keep connection alive, no timeout
                stdin, stdout, stderr = ssh.exec_command(
                    f"/usr/adios/axinstall -b {release}", 
                    get_pty=True
                )
                
                # Wait for command to complete and get exit status
                exit_status = stdout.channel.recv_exit_status()
                if exit_status == 0:
                    logging.info(f"Adios has been Updated for host {hostname}")
                else:
                    logging.error(f"Adios update failed for {hostname} with exit code: {exit_status}")
            except (paramiko.SSHException, OSError) as e:
                logging.error(f"SSH error during Adios update for {hostname}: {str(e)}")
            except Exception as e:
                logging.error(f"Unexpected error during Adios update for {hostname}: {str(e)}")
        
        config_success = False
        try:
            # Check SSH connection is still alive before proceeding
            if not transport or not transport.is_active():
                logging.info(f"Reconnecting to {hostname} for configuration...")
                ssh.close()
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(host, username=username, password=password)
                transport = ssh.get_transport()
                transport.set_keepalive(30)
            
            stdin, stdout, stderr = ssh.exec_command("axcli state | grep STATE | awk 'NR==1'")
            output = stdout.read().decode()
            logging.info(f"Configuring Dispatcher for host {hostname}")
            
            # Run axcli adiosx config and wait for it to return to prompt
            stdin, stdout, stderr = ssh.exec_command("axcli adiosx config", get_pty=True)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0:
                logging.info(f"Dispatcher configured for host {hostname}. Polling for Final Ready State........")
                config_success = True
            else:
                logging.error(f"Dispatcher config failed for {hostname} with exit code: {exit_status}")
        except socket.timeout:
            logging.warning(f"Config command timeout for {hostname}")
        except (paramiko.SSHException, OSError) as e:
            logging.warning(f"SSH error during config for {hostname}: {str(e)}")
        except Exception as e:
            logging.warning(f"Unexpected error during config for {hostname}: {str(e)}")

        # Only poll for Ready state if configuration was successful
        if not config_success:
            logging.warning(f"Skipping Ready state polling for {hostname} due to configuration failure")
        else:
            max_wait_time = 3600  # Maximum 60 minutes wait
            start_time = time.time()
            
            while True:
                self._check_stop()
                
                # Check if we've exceeded max wait time
                if time.time() - start_time > max_wait_time:
                    logging.warning(f"Timeout waiting for {hostname} to be Ready after {max_wait_time} seconds")
                    break
                    
                try:
                    # Check if connection is still alive
                    if not sec_transport or not sec_transport.is_active():
                        logging.info(f"Reconnecting to {hostname} ({host})...")
                        sec_ssh.close()
                        sec_ssh = paramiko.SSHClient()
                        sec_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                        sec_ssh.connect(host, username=username, password=password)
                        sec_transport = sec_ssh.get_transport()
                        sec_transport.set_keepalive(30)
                        
                    stdin, stdout, stderr = sec_ssh.exec_command("axcli state | grep STATE | awk 'NR==1'")
                    output = stdout.read().decode()
                    if "Ready" in output:
                        logging.info(f"{hostname} is Ready")
                        break
                except (paramiko.SSHException, OSError, Exception) as e:
                    logging.warning(f"Connection error for {hostname}: {str(e)}. Attempting to reconnect...")
                    try:
                        sec_ssh.close()
                        sec_ssh = paramiko.SSHClient()
                        sec_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                        sec_ssh.connect(host, username=username, password=password)
                        sec_transport = sec_ssh.get_transport()
                        sec_transport.set_keepalive(30)
                    except Exception as reconnect_error:
                        logging.error(f"Failed to reconnect to {hostname}: {str(reconnect_error)}")
                        break
                        
                time.sleep(5)  # Increased from 1 to 5 seconds to reduce connection overhead

        try:
            ssh.close()
        except:
            pass
        try:
            sec_ssh.close()
        except:
            pass
    
    def ready_hosts(self, vm_details_with_login, release , updateadios ):

        logging.info("------------- Waiting for the Hosts to be In Ready State --------------")
        threads = []
        for vm in vm_details_with_login:

            hostname = vm['hostname'] 
            host = vm['hostip']
            username = vm['username']
            password = vm['password']
            

            if host is not None:
                
                thread = threading.Thread(target=self.execute_command, args=(hostname, host, username, password, release, updateadios))
                threads.append(thread)
                thread.start()
            
        for thread in threads:
            thread.join()
            
    def get_final_adios_version(self, vm_details_with_login):
        """Get the Adios version from a randomly selected available host."""
        if not vm_details_with_login:
            return
        
        # Filter to only VMs with valid credentials and IPs
        connectable_vms = [
            vm for vm in vm_details_with_login
            if vm.get('hostip') and vm.get('username') and vm.get('password')
        ]
        
        if not connectable_vms:
            logging.warning("Could not get Adios version: no VMs with valid credentials")
            return
        
        logging.info("------------- Getting Final Adios Version --------------")
        
        # Shuffle so we try a random VM each time
        candidates = connectable_vms[:]
        random.shuffle(candidates)
        
        for vm in candidates:
            try:
                ssh_final = paramiko.SSHClient()
                ssh_final.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh_final.connect(vm['hostip'], username=vm['username'], password=vm['password'])
                
                stdin, stdout, stderr = ssh_final.exec_command("axcli version")
                version_output = stdout.read().decode().strip()
                ssh_final.close()
                
                if version_output:
                    logging.info(f"Final Adios Version on {vm['hostname']}: {version_output}")
                    return
            except Exception:
                continue
        
        logging.warning("Could not get Adios version from any available host")
    
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
                    else:
                        logging.info("Details Not found in vCenter : " + vcenter['vcenter_server'])

            if found == 1:

                self._check_stop()

                # Deduplicate hosts by name: a standalone ESX host can appear in matched_hosts
                # as BOTH a vim.ComputeResource and a vim.HostSystem (same .name). Prefer HostSystem.
                _unique_hosts = {}
                for _h in matched_hosts:
                    if _h.name not in _unique_hosts or isinstance(_h, vim.HostSystem):
                        _unique_hosts[_h.name] = _h
                matched_hosts = list(_unique_hosts.values())

                # Deduplicate VMs by name as a safety net
                _unique_vms = {}
                for _vm in matched_vms:
                    if _vm.name not in _unique_vms:
                        _unique_vms[_vm.name] = _vm
                matched_vms = list(_unique_vms.values())

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
                    self.get_final_adios_version(match_vms_with_cred)
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
                    self.get_final_adios_version(match_vms_with_cred)
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
                    self.get_final_adios_version(match_vms_with_cred)
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
                    self.get_final_adios_version(match_vms_with_cred)
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