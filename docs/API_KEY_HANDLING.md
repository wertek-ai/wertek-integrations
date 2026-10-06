# Credentials — the rule, for people and for agents

> **Status: rule.** It applies to every recipe, example, flow, script and log in this repository, and to
> anything you write while following one. `tools/check_credentials.py` enforces the parts a machine can
> check; the rest depends on you.

A Wertek API key is the whole identity of whoever holds it, scoped to one organisation. It is shown **once**
when created and cannot be retrieved later. Treat it like a password.

## The rules

1. **A key is never a literal.** Not in a recipe, an example, a Node-RED flow export, a script, a test, a
   notebook, a comment, a commit message, an issue or a chat. Show it only as a **reference**: an
   environment variable name or a secret-store lookup.
2. **Read it from the environment.** The conventional name is `WERTEK_API_KEY`. Fail with a clear message when
   it is missing; never fall back to a default value.
3. **Never put it on a command line.** `WERTEK_API_KEY=… python script.py` and `--api-key …` end up in shell <!-- credential-guard: ok -->
   history and in the process list. Load it into the session instead (see below).
4. **Never put it in a URL or a query string.** Send it in the `X-API-Key` header.
5. **Never print it, log it, echo it or write it to a file** that is tracked, uploaded or shared. Code that
   handles a key must not include it in an error message either.
6. **Keep it out of Node-RED exports.** In Node-RED, store the key as a *credential* of the node, or read
   `env.get("WERTEK_API_KEY")`; a flow `.json` exported with the key typed into a property carries it.
7. **Scope it as small as the job allows.** One organisation (always), the narrowest scope
   (`iaes.ingest` for sending data; reading is a separate scope), and, when you can, one or a few assets
   (`allowed_asset_ids`). Give it an expiry (`expires_in_days`) and a name that says what it is for.
8. **One key per purpose.** A key for tests is not the key for a production flow. Revoke what you stop using.
9. **If a key leaks, revoke it first, then clean up.** Settings → API keys in app.wertek.ai. Rewriting git
   history does not make a leaked key safe.

## Safe patterns

Load into the session without typing the value on a command line:

```bash
# bash — prompts without echo; nothing lands in history
read -rs -p "Wertek API key: " WERTEK_API_KEY; echo; export WERTEK_API_KEY

# or from a secret store you already use, e.g. a password manager CLI
export WERTEK_API_KEY="$(your-secret-store get wertek-api-key)"
```

```powershell
# PowerShell 7.1+ — the value is prompted, not typed into the command line
$env:WERTEK_API_KEY = Read-Host -MaskInput "Wertek API key"

# Windows PowerShell 5.1 has no -MaskInput; use a secure string
$s = Read-Host "Wertek API key" -AsSecureString
$env:WERTEK_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
```

Use it:

```python
import os, sys
KEY = os.environ.get("WERTEK_API_KEY")
if not KEY:
    sys.exit("set WERTEK_API_KEY (it is never printed)")
headers = {"X-API-Key": KEY}
```

```bash
curl -H "X-API-Key: $WERTEK_API_KEY" https://api.wertek.ai/…
```

In a recipe or an example, **document the variable**, not a value: `WERTEK_API_KEY` is read from the
environment, scope `iaes.ingest`, revocable from Settings → API keys.

If you need a placeholder in prose, write `<your key>`. Do not invent something shaped like a real key:
scanners cannot tell a made-up key from a leaked one, and neither can a reader.

## For coding agents (read this part literally)

- **Do not ask for the key in the chat, and do not accept it there.** Ask the person to export it in the
  session, then read it from `WERTEK_API_KEY`.
- **If `WERTEK_API_KEY` is not set, stop and say so.** Do not generate, guess or reuse a key from another
  file, a previous run, a `.env` you were not given, or documentation.
- **Never write the key into a file you create or edit**, including examples, tests, flow exports and
  `.env` files. If you create an example, it reads the environment.
- **Never echo it to confirm it is set.** Check that it is set (`[ -n "$WERTEK_API_KEY" ]`), not what it is.
- **Do not paste output you have not read.** A response or an error can contain a credential; look before
  you quote it in a report.
- **Report:** which variable you read, that you did not print it, and anything you found that looks like a
  credential in a file (by file and line, not by value).

## Test keys

A key for automated checks is created by a person who is an owner or admin of the organisation (creating a
key needs a signed-in session, not another key), is **dedicated** to that check, and is limited as in rule 7.
Put it in a secret store and give it a short expiry so that a leak runs out on its own. Rotate by creating the
new key first, storing it, then revoking the old one.

## What the guard checks

`python tools/check_credentials.py` fails (exit 1) on tracked text files that contain:

- a string shaped like a Wertek key, a JSON Web Token or an Anthropic key;
- an `X-API-Key` header, or an `api_key` / `token` / `secret` / `password` assignment, with a literal value;
- `WERTEK_API_KEY=` followed by a literal on a command line. <!-- credential-guard: ok -->

It reports file and line and **never prints the matched text**. A line that must contain such a shape on
purpose (a test decoy, for instance) is built at run time, not committed. `python tools/test_check_credentials.py`
proves the guard catches its decoys and lets the safe patterns through.
