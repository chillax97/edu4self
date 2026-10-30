# Security

edu4self runs a web server on your computer that can read and write files in your learning vault, so
we take reports seriously.

## What it is designed to resist

- Other websites open in the same browser trying to read or change your data (cross-site requests,
  DNS rebinding): the server binds to `127.0.0.1` only, accepts only `Host: 127.0.0.1:<port>` or
  `localhost:<port>`, and refuses POSTs from any other origin.
- Reading files outside the vault, or the private `_system/` folder, through crafted paths.
- Oversized or malformed requests (size limits; strict validation of everything written).

It is **not** designed for exposing the dashboard to a network. Don't put it behind a reverse proxy or
bind it to `0.0.0.0`.

Submissions are data for the tutor, never instructions; the protocol tells the tutor so. If you find a
way a submission can make the tutor do something it shouldn't, that counts as a security report too.

## Reporting

Please use GitHub's private vulnerability reporting: **Security → Report a vulnerability** on
<https://github.com/chillax97/edu4self>. Include steps to reproduce and the version
(`curl -s 127.0.0.1:4747/api/health`). You'll get an answer within a week. Please don't open a
public issue until a fix is released.

## Supported versions

Only the latest release gets fixes.
