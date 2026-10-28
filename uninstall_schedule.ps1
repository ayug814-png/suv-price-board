# Stops the automatic refresh. The board and its history stay where they are.
Unregister-ScheduledTask -TaskName "SUV Price Board" -Confirm:$false
"Removed the 'SUV Price Board' scheduled task."
