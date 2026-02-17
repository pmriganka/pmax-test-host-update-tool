import os
import json
import requests
import base64
import logging
import time
import ssl
import atexit
from dotenv import load_dotenv
from datetime import datetime
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim

load_dotenv()

class HybridHostRemediation:
    """
    Hybrid ESX Host Remediation System
    Combines pyVmomi for health checks with vCenter REST API for patch remediation
    """
    
    def __init__(self):
        # Use your existing vCenter configuration
        self.all_data_centers = [
            {
                "vcenter_server": f"{os.getenv('vcenter_est_hop_server')}",
                "username": f"{os.getenv('vcenter_est_hop_username')}",
                "password": f"{os.getenv('vcenter_est_hop_password')}"
            }
            # Add other vCenters as needed
        ]
        
        # vCenter REST API setup
        self.vcenter_url = os.getenv('vcenter_est_hop_server')
        self.vcenter_username = os.getenv('vcenter_est_hop_username')
        self.vcenter_password = os.getenv('vcenter_est_hop_password')
        self.rest_session_id = None
        self.si = None
        self.content = None
    
    # ==================== EXISTING METHODS FROM HOST_MANAGEMENT ====================
    
    def connect_vcenter(self, vcenter, username, password):
        """Connect to vCenter using pyVmomi"""
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.verify_mode = ssl.CERT_NONE
        
        self.si = SmartConnect(
            host=vcenter,
            user=username,
            pwd=password,
            port=443,
            sslContext=context
        )
        atexit.register(Disconnect, self.si)
        return self.si
    
    def get_container_view(self, content, container):
        """Get container view for vCenter objects"""
        vimTypes = [vim.Folder, vim.VirtualMachine, vim.ComputeResource, vim.HostSystem]
        view = content.viewManager.CreateContainerView(container, vimTypes, True)
        objs = list(view.view)
        view.Destroy()
        return objs
    
    def find_folder_by_name(self, content, system_name):
        """Find folder by name in vCenter"""
        container = self.get_container_view(content, content.rootFolder)
        for folder in container:
            if system_name in folder.name:
                return folder
        return None
    
    def get_hosts_and_vms_from_folder(self, content, folder):
        """Get hosts and VMs from a specific folder"""
        hosts = set()
        vms = set()
        
        entity = self.get_container_view(content, folder)
        for child in entity:
            if isinstance(child, vim.ComputeResource):
                hosts.add(child)
                for vm in child.resourcePool.vm:
                    vms.add(vm)
            elif isinstance(child, vim.HostSystem):
                hosts.add(child)
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
        """Find VMs and hosts by system name"""
        hosts = set()
        vms = set()
        all_details = {}
        
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
    
    # ==================== HYBRID REMEDIATION METHODS ====================
    
    def quick_health_check(self, host):
        """
        Fast health analysis using pyVmomi host object
        """
        issues = []
        needs_remediation = False
        severity = 'low'
        
        try:
            # Connection check
            if host.summary.runtime.connectionState != vim.HostSystem.ConnectionState.connected:
                issues.append(f"Connection: {host.summary.runtime.connectionState}")
                needs_remediation = True
                severity = 'high'
            
            # Maintenance mode check
            if host.runtime.inMaintenanceMode:
                issues.append("Stuck in maintenance mode")
                needs_remediation = True
                severity = 'medium'
            
            # Health status check
            if hasattr(host.summary, 'overallStatus') and host.summary.overallStatus != vim.ManagedEntity.Status.green:
                issues.append(f"Health: {host.summary.overallStatus}")
                needs_remediation = True
                severity = 'medium'
            
            # Memory usage check
            if hasattr(host.summary, 'quickStats') and host.summary.quickStats:
                memory_usage = host.summary.quickStats.overallMemoryUsage
                if memory_usage and host.summary.hardware.memorySize:
                    usage_pct = (memory_usage * 1024 * 1024) / host.summary.hardware.memorySize * 100
                    if usage_pct > 90:
                        issues.append(f"High memory: {usage_pct:.1f}%")
                        needs_remediation = True
                        severity = 'medium'
            
            # Hardware issues check
            if hasattr(host.summary.hardware, 'numCpuCores') and host.summary.hardware.numCpuCores == 0:
                issues.append("Hardware configuration issue")
                needs_remediation = True
                severity = 'high'
            
            logging.info(f"Health check for {host.name}: {'Needs remediation' if needs_remediation else 'Compliant'}")
            if issues:
                logging.info(f"  Issues: {', '.join(issues)}")
            
        except Exception as e:
            logging.error(f"Error during health check for {host.name}: {str(e)}")
            issues.append(f"Health check error: {str(e)}")
            needs_remediation = True
            severity = 'high'
        
        return {
            'needs_remediation': needs_remediation,
            'issues': issues,
            'severity': severity
        }
    
    def quick_custom_remediate(self, host):
        """
        Custom remediation using pyVmomi operations
        """
        try:
            logging.info(f"Starting custom remediation for {host.name}")
            
            # Enter maintenance mode
            if not host.runtime.inMaintenanceMode:
                logging.info(f"Entering maintenance mode for {host.name}")
                task = host.EnterMaintenanceMode_Task(timeout=300, evacuatePoweredOffVms=False)
                
                while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
                    logging.info(f"Waiting for maintenance mode... Progress: {task.info.progress}%")
                    time.sleep(5)
                
                if task.info.state != vim.TaskInfo.State.success:
                    logging.error(f"Failed to enter maintenance mode: {task.info.error}")
                    return False
                else:
                    logging.info(f"Successfully entered maintenance mode")
            
            # Perform remediation operations
            logging.info("Performing remediation operations...")
            
            # Refresh storage configuration
            try:
                if hasattr(host, 'configManager') and host.configManager.storageSystem:
                    logging.info("Refreshing storage configuration...")
                    host.configManager.storageSystem.RefreshStorageInfo()
                    time.sleep(5)
                    logging.info("Storage configuration refreshed")
            except Exception as e:
                logging.warning(f"Could not refresh storage info: {str(e)}")
            
            # Check and restart management agents
            try:
                if hasattr(host, 'configManager') and host.configManager.serviceSystem:
                    logging.info("Checking management agents...")
                    services = host.configManager.serviceSystem.serviceInfo.service
                    for service in services:
                        if service.key in ['vpxa', 'hostd']:
                            if not service.running:
                                logging.info(f"Starting management agent {service.key}...")
                                host.configManager.serviceSystem.StartService(service.key)
                                time.sleep(10)
                            else:
                                logging.info(f"Management agent {service.key} is running")
            except Exception as e:
                logging.warning(f"Could not check management agents: {str(e)}")
            
            # Validate network configuration
            try:
                if hasattr(host, 'configManager') and host.configManager.networkSystem:
                    logging.info("Validating network configuration...")
                    network_system = host.configManager.networkSystem
                    network_system.RefreshNetworkConfig(timeout=30)
                    logging.info("Network configuration validated")
            except Exception as e:
                logging.warning(f"Could not validate network config: {str(e)}")
            
            # Check storage connectivity
            try:
                if hasattr(host, 'configManager') and host.configManager.storageSystem:
                    logging.info("Checking storage connectivity...")
                    storage_system = host.configManager.storageSystem
                    storage_system.RescanAllHba()
                    time.sleep(10)
                    logging.info("Storage connectivity checked")
            except Exception as e:
                logging.warning(f"Could not check storage: {str(e)}")
            
            # Exit maintenance mode
            logging.info(f"Exiting maintenance mode for {host.name}")
            task = host.ExitMaintenanceMode_Task(timeout=300)
            
            while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
                logging.info(f"Waiting to exit maintenance mode... Progress: {task.info.progress}%")
                time.sleep(5)
            
            if task.info.state == vim.TaskInfo.State.success:
                logging.info(f"Successfully exited maintenance mode")
                
                # Wait for host to be fully operational
                logging.info("Waiting for host to become fully operational...")
                max_wait_time = 300  # 5 minutes
                start_time = time.time()
                
                while time.time() - start_time < max_wait_time:
                    try:
                        if (host.summary.runtime.connectionState == vim.HostSystem.ConnectionState.connected and 
                            not host.runtime.inMaintenanceMode):
                            logging.info(f"Host {host.name} is fully operational")
                            break
                    except:
                        pass
                    time.sleep(10)
                
                logging.info(f"✅ Custom remediation successful for {host.name}")
                return True
            else:
                logging.error(f"Failed to exit maintenance mode: {task.info.error}")
                return False
                
        except Exception as e:
            logging.error(f"Error during custom remediation for {host.name}: {str(e)}")
            return False
    
    def get_vcenter_session(self):
        """Get vCenter REST API session for patch remediation"""
        if not self.rest_session_id:
            try:
                auth = base64.b64encode(
                    f"{self.vcenter_username}:{self.vcenter_password}".encode()
                ).decode()
                
                headers = {'Authorization': f'Basic {auth}'}
                response = requests.post(
                    f"{self.vcenter_url}/api/session",
                    headers=headers,
                    verify=False
                )
                
                if response.status_code == 200:
                    self.rest_session_id = response.json()
                    logging.info("Successfully obtained vCenter REST API session")
                else:
                    logging.error(f"Failed to get vCenter session: {response.status_code} - {response.text}")
                    return None
                    
            except Exception as e:
                logging.error(f"Error getting vCenter session: {str(e)}")
                return None
        
        return self.rest_session_id
    
    def get_cluster_id(self, cluster_name, session_id):
        """Get cluster ID by name using vCenter REST API"""
        try:
            headers = {'vmware-api-session-id': session_id}
            response = requests.get(
                f"{self.vcenter_url}/api/vcenter/cluster",
                headers=headers,
                verify=False
            )
            
            if response.status_code == 200:
                clusters = response.json()
                for cluster in clusters:
                    if cluster['name'] == cluster_name:
                        return cluster['cluster']
            
            logging.warning(f"Cluster '{cluster_name}' not found")
            return None
            
        except Exception as e:
            logging.error(f"Error getting cluster ID: {str(e)}")
            return None
    
    def get_host_ids_by_name(self, cluster_id, session_id, host_names):
        """Get host IDs by names using vCenter REST API"""
        try:
            headers = {'vmware-api-session-id': session_id}
            response = requests.get(
                f"{self.vcenter_url}/api/vcenter/host",
                headers=headers,
                verify=False
            )
            
            if response.status_code == 200:
                hosts = response.json()
                host_ids = []
                
                for host in hosts:
                    # Match host names
                    for host_name in host_names:
                        if host_name in host['name']:
                            host_ids.append(host['host'])
                            break
                
                return host_ids
            
            logging.error(f"Failed to get host information: {response.status_code}")
            return []
            
        except Exception as e:
            logging.error(f"Error getting host IDs: {str(e)}")
            return []
    
    def quick_patch_remediate(self, cluster_name, host_names):
        """
        Patch remediation using vCenter REST API
        """
        try:
            logging.info(f"Starting patch remediation for hosts: {host_names}")
            
            session_id = self.get_vcenter_session()
            if not session_id:
                return False
            
            # Get cluster ID
            cluster_id = self.get_cluster_id(cluster_name, session_id)
            if not cluster_id:
                return False
            
            # Get host IDs
            host_ids = self.get_host_ids_by_name(cluster_id, session_id, host_names)
            if not host_ids:
                logging.warning("No host IDs found for patch remediation")
                return False
            
            # Start remediation
            headers = {'vmware-api-session-id': session_id}
            payload = {
                'accept_eula': True,
                'hosts': host_ids
            }
            
            response = requests.post(
                f"{self.vcenter_url}/api/esx/settings/clusters/{cluster_id}/software?action=apply",
                headers=headers,
                json=payload,
                verify=False
            )
            
            if response.status_code == 200:
                logging.info(f"✅ Patch remediation started for hosts: {host_names}")
                logging.info(f"Task ID: {response.json()}")
                return True
            else:
                logging.error(f"❌ Patch remediation failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logging.error(f"Error in patch remediation: {str(e)}")
            return False
    
    def hybrid_remediate_box(self, boxname, enable_patches=False):
        """
        Complete hybrid remediation using existing discovery methods
        Args:
            boxname: System/box name to remediate
            enable_patches: Whether to enable patch remediation
        """
        results = {
            'box_name': boxname,
            'total_hosts': 0,
            'custom_remediated': 0,
            'patch_remediated': 0,
            'compliant': 0,
            'failed': 0,
            'details': []
        }
        
        boxname = boxname.upper()
        found = 0
        matched_hosts = None
        found_content = None
        
        logging.info(f"Starting hybrid remediation for box: {boxname}")
        
        # Use existing discovery logic
        for vcenter in self.all_data_centers:
            try:
                # Connect using existing method
                logging.info(f"Connecting to vCenter: {vcenter['vcenter_server']}")
                self.si = self.connect_vcenter(vcenter['vcenter_server'], vcenter['username'], vcenter['password'])
                self.content = self.si.RetrieveContent()
                
                # Find folder using existing method
                folder = self.find_folder_by_name(self.content, boxname)
                
                if folder:
                    logging.info(f"Found folder '{folder.name}' in vCenter: {vcenter['vcenter_server']}")
                    found = 1
                    logging.info("Details found in vCenter: " + vcenter['vcenter_server'])
                    
                    # Get hosts and VMs using existing method
                    matched_hosts, matched_vms = self.get_hosts_and_vms_from_folder(self.content, folder)
                    found_content = self.content
                    break
                else:
                    logging.info(f"Folder '{boxname}' not found in vCenter: {vcenter['vcenter_server']}")
                    
                    # Try fallback to system name search
                    all_details = self.find_vms_with_system_name(self.content, boxname)
                    if all_details['hosts'] and all_details['vms']:
                        found = 1
                        matched_hosts, matched_vms = all_details['hosts'], all_details['vms']
                        found_content = self.content
                        break
                        
            except Exception as e:
                logging.error(f"Error connecting to vCenter {vcenter['vcenter_server']}: {str(e)}")
                continue
        
        if found == 0 or not matched_hosts:
            logging.error(f"No hosts found for {boxname}")
            return results
        
        # Convert set to list for processing
        host_list = list(matched_hosts)
        results['total_hosts'] = len(host_list)
        
        logging.info(f"Found {len(host_list)} hosts for {boxname}:")
        for host in host_list:
            logging.info(f"  Host: {host.name}")
        
        # Process each host
        for host in host_list:
            host_result = {
                'name': host.name,
                'custom_done': False,
                'patch_done': False,
                'issues': []
            }
            
            try:
                # Health check
                health = self.quick_health_check(host)
                host_result['issues'] = health['issues']
                
                # Custom remediation
                if health['needs_remediation']:
                    logging.info(f"Performing custom remediation on {host.name}")
                    success = self.quick_custom_remediate(host)
                    if success:
                        host_result['custom_done'] = True
                        results['custom_remediated'] += 1
                        logging.info(f"✅ Custom remediation successful for {host.name}")
                    else:
                        results['failed'] += 1
                        logging.error(f"❌ Custom remediation failed for {host.name}")
                        results['details'].append(host_result)
                        continue
                else:
                    logging.info(f"✅ Host {host.name} is compliant - no remediation needed")
                    results['compliant'] += 1
                
                # Patch remediation (optional)
                if enable_patches:
                    logging.info(f"Performing patch remediation on {host.name}")
                    patch_success = self.quick_patch_remediate(boxname, [host.name])
                    if patch_success:
                        host_result['patch_done'] = True
                        results['patch_remediated'] += 1
                        logging.info(f"✅ Patch remediation started for {host.name}")
                    else:
                        logging.warning(f"⚠️ Patch remediation failed for {host.name}")
                
                results['details'].append(host_result)
                
            except Exception as e:
                logging.error(f"Error processing {host.name}: {str(e)}")
                results['failed'] += 1
                results['details'].append(host_result)
        
        return results

# ==================== USAGE EXAMPLE ====================

def main():
    """
    Example usage of HybridHostRemediation
    """
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Initialize hybrid remediation
    hybrid = HybridHostRemediation()
    
    # Test with a box name
    boxname = "OGH5"  # Test with OGH5
    
    logging.info("=== Hybrid Remediation Test ===")
    
    # Run hybrid remediation
    results = hybrid.hybrid_remediate_box(
        boxname=boxname,
        enable_patches=False  # Set to True to enable patch remediation
    )
    
    # Print results
    logging.info("=== Hybrid Remediation Results ===")
    logging.info(f"Box: {results['box_name']}")
    logging.info(f"Total hosts: {results['total_hosts']}")
    logging.info(f"Custom remediated: {results['custom_remediated']}")
    logging.info(f"Patch remediated: {results['patch_remediated']}")
    logging.info(f"Compliant: {results['compliant']}")
    logging.info(f"Failed: {results['failed']}")
    
    # Detailed breakdown
    logging.info("=== Detailed Results ===")
    for detail in results['details']:
        status_parts = []
        if detail['custom_done']:
            status_parts.append("Custom")
        if detail['patch_done']:
            status_parts.append("Patch")
        
        status = " | ".join(status_parts) if status_parts else "Compliant"
        logging.info(f"{detail['name']}: {status}")
        
        if detail['issues']:
            logging.info(f"  Issues: {', '.join(detail['issues'])}")

if __name__ == "__main__":
    main()