param(
    [string]$SshHost = "hydro-rt-30753",
    [string]$IdentityFile = "$HOME/.ssh/id_ed25519_hydro3d",
    [string]$ControlHost = "172.16.224.4",
    [int]$ControlAgentPort = 18080,
    [int]$ControlMinioPort = 19000,
    [int]$RemoteAgentPort = 28080,
    [int]$RemoteMinioPort = 29000
)

$signature = "$RemoteAgentPort`:$ControlHost`:$ControlAgentPort"
$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "ssh.exe" -and $_.CommandLine -like "*$signature*"
}
if ($existing) {
    Write-Output "Reverse tunnel is already running (PID $($existing.ProcessId))."
    exit 0
}

$ssh = (Get-Command ssh -ErrorAction Stop).Source
$arguments = @(
    "-N", "-T", "-i", $IdentityFile,
    "-o", "IdentitiesOnly=yes",
    "-o", "ExitOnForwardFailure=yes",
    "-o", "ServerAliveInterval=15",
    "-o", "ServerAliveCountMax=3",
    "-R", "$RemoteAgentPort`:$ControlHost`:$ControlAgentPort",
    "-R", "$RemoteMinioPort`:$ControlHost`:$ControlMinioPort",
    $SshHost
)
$process = Start-Process -FilePath $ssh -ArgumentList $arguments -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2
if ($process.HasExited) {
    throw "Reverse tunnel exited with code $($process.ExitCode)."
}
Write-Output "Reverse tunnel started (PID $($process.Id))."
