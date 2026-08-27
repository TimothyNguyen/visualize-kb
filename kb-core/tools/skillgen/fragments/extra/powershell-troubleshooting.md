## Troubleshooting

### PowerShell 5.1: Vertical scrolling stops working

If vertical scrolling breaks in PowerShell after running kb-core, this is caused by ANSI escape sequences from the `graspologic` library. KB Core v0.3.10+ suppresses this output, but if you still see the issue:

1. **Upgrade kb-core**: `pip install --upgrade kb-core`
2. **Use Windows Terminal** instead of the legacy PowerShell console — Windows Terminal handles ANSI codes correctly
3. **Reset your terminal**: close and reopen PowerShell
4. **Skip graspologic**: uninstall it (`pip uninstall graspologic`) and kb-core will fall back to NetworkX's built-in Louvain algorithm, which produces no ANSI output

---
