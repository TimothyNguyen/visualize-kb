# harness web dir

A fixed stand-in for `web/dist`, passed to both engines as `--web-dir`.

`web/dist` is a build artifact and is not committed, so a fresh checkout
has none -- both engines would then serve API-only and the spa-serving
fixture would compare two 404s and pass without testing anything. Its
asset names are also content-hashed, so a rebuild would silently break
any manifest that referenced them.

These files are deliberately tiny and hash-free: the handler under test
is the static/SPA-fallback path, not the real bundle.
