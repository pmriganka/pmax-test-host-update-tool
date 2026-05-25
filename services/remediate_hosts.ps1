param(
    [Parameter(Mandatory=$true)][string]$VCenter,
    [Parameter(Mandatory=$true)][string]$Username,
    [Parameter(Mandatory=$true)][string]$Password,
    [Parameter(Mandatory=$true)][string]$HostNames
)

# Verify PowerCLI is installed
$pcli = Get-Module -ListAvailable VMware.PowerCLI 2>$null
if (-not $pcli) {
    Write-Output "ERROR VMware.PowerCLI module is not installed. Run: Install-Module -Name VMware.PowerCLI -Scope CurrentUser -Force"
    exit 1
}

# Import PowerCLI modules
Import-Module VMware.PowerCLI -ErrorAction Stop

# Suppress CEIP warning and ignore invalid certs
Set-PowerCLIConfiguration -Scope User -ParticipateInCEIP $false -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
Set-PowerCLIConfiguration -InvalidCertificateAction Ignore -Confirm:$false -ErrorAction SilentlyContinue | Out-Null

$secPassword = ConvertTo-SecureString $Password -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential($Username, $secPassword)

try {
    # Connect to vCenter
    $server = Connect-VIServer -Server $VCenter -Credential $cred -ErrorAction Stop
    Write-Output "CONNECTED to $VCenter"

    $hostList = $HostNames -split ","

    foreach ($hostName in $hostList) {
        $hostName = $hostName.Trim()
        Write-Output "PROCESSING $hostName"

        $vmHost = Get-VMHost -Name $hostName -ErrorAction Stop

        # Scan for compliance
        Write-Output "SCANNING $hostName"
        $vmHost | Test-Compliance -ErrorAction Stop | Out-Null

        # Get compliance status
        $compliance = $vmHost | Get-Compliance -ErrorAction Stop
        $nonCompliant = $compliance | Where-Object { $_.Status -ne "Compliant" }

        if ($nonCompliant) {
            Write-Output "NON_COMPLIANT $hostName - Starting remediation"
            
            # Get attached baselines that are non-compliant
            $baselines = $nonCompliant | Select-Object -ExpandProperty Baseline

            foreach ($baseline in $baselines) {
                Write-Output "REMEDIATING $hostName against baseline: $($baseline.Name)"
                $vmHost | Remediate-Inventory -Baseline $baseline -HostFailureAction Retry -Confirm:$false -ErrorAction Stop
                Write-Output "REMEDIATED $hostName against baseline: $($baseline.Name)"
            }
        } else {
            Write-Output "COMPLIANT $hostName"
        }
    }

    Write-Output "SUCCESS All hosts processed"
} catch {
    Write-Output "ERROR $($_.Exception.Message)"
    exit 1
} finally {
    if ($server) {
        Disconnect-VIServer -Server $VCenter -Confirm:$false -ErrorAction SilentlyContinue
    }
}
