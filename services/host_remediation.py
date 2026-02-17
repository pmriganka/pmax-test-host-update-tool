import requests
import urllib3
import logging
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_session(vcenter, username, password):
    """Create a vCenter REST API session and return session ID."""
    url = f"https://{vcenter}/rest/com/vmware/cis/session"
    response = requests.post(url, auth=(username, password), verify=False)
    response.raise_for_status()
    return response.json()['value']

def check_compliance(vcenter, session_id, host_id):
    """Check host compliance status via vSphere Lifecycle Manager REST API."""
    url = f"https://{vcenter}/api/esx/settings/hosts/{host_id}/software/compliance"
    headers = {"vmware-api-session-id": session_id}
    response = requests.get(url, headers=headers, verify=False)
    if response.status_code == 200:
        return response.json()
    else:
        logging.warning(f"Compliance check returned {response.status_code} for {host_id}")
        return None

def remediate_host(vcenter, session_id, host_id):
    """Trigger remediation for a host via vSphere Lifecycle Manager REST API."""
    url = f"https://{vcenter}/api/esx/settings/hosts/{host_id}/software?action=apply"
    headers = {"vmware-api-session-id": session_id}
    response = requests.post(url, headers=headers, verify=False)
    if response.status_code in [200, 202]:
        return response.json() if response.text else True
    else:
        logging.error(f"Remediation request failed with {response.status_code}: {response.text}")
        return None

def poll_task(vcenter, session_id, task_id, timeout=1800):
    """Poll a vCenter task until completion."""
    url = f"https://{vcenter}/api/cis/tasks/{task_id}"
    headers = {"vmware-api-session-id": session_id}
    end_time = time.time() + timeout

    while time.time() < end_time:
        response = requests.get(url, headers=headers, verify=False)
        if response.status_code == 200:
            task_info = response.json()
            status = task_info.get('status', '')
            if status == 'SUCCEEDED':
                logging.info("Remediation task completed successfully.")
                return True
            elif status == 'FAILED':
                logging.error(f"Remediation task failed: {task_info.get('error', 'Unknown error')}")
                return False
        logging.info("Remediation in progress...")
        time.sleep(30)

    logging.error("Remediation task timed out.")
    return False

def host_remediation(vcenter, username, password, hosts):
    """Check compliance and remediate non-compliant hosts."""

    logging.info("------------- Host Remediation for New Patches --------------")
    session_id = get_session(vcenter, username, password)
    logging.info(f"vCenter REST session established for {vcenter}")

    for host in hosts:
        host_id = host._moId
        host_name = host.name
        logging.info(f"Checking compliance for {host_name} ({host_id})...")

        compliance = check_compliance(vcenter, session_id, host_id)

        if compliance is None:
            logging.warning(f"Could not check compliance for {host_name}. Skipping.")
            continue

        status = compliance.get('status', '')
        if status == 'NON_COMPLIANT':
            logging.info(f"Host {host_name} is Non-Compliant. Starting remediation...")
            result = remediate_host(vcenter, session_id, host_id)

            if isinstance(result, dict) and 'task' in result:
                poll_task(vcenter, session_id, result['task'])
            elif result:
                logging.info(f"Remediation completed for {host_name}")
            else:
                logging.error(f"Remediation failed for {host_name}")
        else:
            logging.info(f"Host {host_name} is in compliance ({status}). No action needed.")