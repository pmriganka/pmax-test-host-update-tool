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
