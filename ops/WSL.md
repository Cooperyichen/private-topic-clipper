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
   effect when WSL next starts. The script also creates the independent Windows
   task `Clipper WSL Keepalive`, using the current Windows account with S4U
   logon and limited privileges. It stores no password and runs `wsl.exe`
   with `/usr/bin/sleep infinity`. Boot and recurring minute triggers start
   the task; an unlimited execution time and `IgnoreNew` prevent duplicate
   keepalive processes. Existing tasks with a different action cause an error.
   Run the installer with permission to register this task. Ubuntu is not
   restarted. Running the script again reuses the running task.
3. Check that `Get-ScheduledTask -TaskName 'Clipper WSL Keepalive'` reports
   `Running`. Close the diagnostic Windows SSH shell before the quiet-interval
   verification. A `Start-Process` child launched through Windows SSH/interop
   was observed to disappear when that session ended; only the task-owned
   process is relied upon for persistence.

The installed WSL version at verification was 2.7.8.0. See Microsoft's
[WSL settings](https://learn.microsoft.com/en-us/windows/wsl/wsl-config) and
[systemd lifecycle documentation](https://learn.microsoft.com/en-us/windows/wsl/systemd).

## Verify and roll back

Check the API and worker with `systemctl --user is-active clipper-api clipper-worker`
and the timer with `systemctl --user is-active clipper-backup.timer`. Check the
HTTPS homepage and `/api/v1/clips` from another tailnet device after a quiet
interval longer than the previous idle shutdown window. An HTTP request alone
must not be relied upon to keep WSL running.

To undo, stop and unregister only the `Clipper WSL Keepalive` task, then
restore the original printed `.wslconfig.clipper-*.bak` file to `.wslconfig`
and run `loginctl disable-linger coope` if session-scoped services are desired.
Configuration rollback takes effect on the next WSL start. Avoid terminating WSL while other work is
running. Windows sleep and shutdown still make the service unavailable.
