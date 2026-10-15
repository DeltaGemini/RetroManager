# Windows PowerShell script to SSH into the Pi and run docker compose commands in the project directory
# Copy to dev-ssh.ps1 and fill in the four values below.
# Usage: .\dev-ssh.ps1 "docker compose up -d" (or any docker command)

param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$DockerCommand
)

$sshUser = "pi"
$sshHost = "192.0.2.10"   # your Pi or NAS
$sshPort = 22
$projectDir = "/path/to/RetroManager"

# Build the SSH command
$fullCommand = "cd $projectDir && $DockerCommand"

ssh -t -p $sshPort "$sshUser@$sshHost" $fullCommand
