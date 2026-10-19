# WSL persistence

The Windows host must stay powered on and connected to Tailscale. WSL systemd
services alone do not prevent an idle distribution from stopping.

## Enable persistence

1. In Ubuntu, run `loginctl enable-linger coope`. Check that
   `loginctl show-user coope -p Linger` reports `Linger=yes`. This starts the
   enabled API, worker and backup timer without requiring a login session.
2. Copy `enable-wsl-persistence.ps1` to a local Windows directory and run it
   in Windows PowerShell. If the system blocks local scripts, use a policy
   scoped to that PowerShell process:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\enable-wsl-persistence.ps1
   ```

   The script backs up an existing `%UserProfile%\.wslconfig`, preserves other
   settings, and sets `[general] instanceIdleTimeout=-1`. This policy takes
   effect when WSL next starts. For the current session it starts a hidden
   Windows `wsl.exe` process running `/usr/bin/sleep infinity`, without restarting
   Ubuntu or interrupting other workloads. Running the script again reuses
   that keepalive process.
3. On this ThinkPad, the existing enabled Windows task
   `Windows Tailscale WSL SSH Bridge` starts Ubuntu at Windows boot and every
   minute. Keep that task enabled. The script does not create or modify tasks.

The installed WSL version at verification was 2.7.8.0. See Microsoft's
[WSL settings](https://learn.microsoft.com/en-us/windows/wsl/wsl-config) and
[systemd lifecycle documentation](https://learn.microsoft.com/en-us/windows/wsl/systemd).

## Verify and roll back

Check the API and worker with `systemctl --user is-active clipper-api clipper-worker`
and the timer with `systemctl --user is-active clipper-backup.timer`. Check the
HTTPS homepage and `/api/v1/clips` from another tailnet device after a quiet
interval longer than the previous idle shutdown window. An HTTP request alone
must not be relied upon to keep WSL running.

To undo, restore the printed `.wslconfig.clipper-*.bak` file to `.wslconfig`
and run `loginctl disable-linger coope` if session-scoped services are desired.
Stop only the Windows keepalive PID printed by the script. Configuration rollback
takes effect on the next WSL start. Avoid terminating WSL while other work is
running. Windows sleep and shutdown still make the service unavailable.
