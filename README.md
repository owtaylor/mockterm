# mockterm

Mockterm is a command line utility that lets an autonomous AI agent test
changes to TUI programs by providing a headless terminal backed by tmux.

## Instructions for agents how to use mockterm

The `mockterm` command is present in your environment.  Run `mockterm --help`
for a full usage summary including all subcommands and flags.

```
mockterm start [-s ID] [--size=<COLS>x<ROWS>] <COMMAND> <ARG>...
```

Start a command.  Session state is written to `.mockterm` in the current
directory.  If a session with the same ID already exists it is killed first.
The underlying tmux session name includes a random tag so that multiple agents
working in the same directory do not collide even when using the same logical
session ID.

```
mockterm grep [-s ID] [--wait] [-t <TIMEOUT>] [-A <NUM>] [-B <NUM>] [-C <NUM>] PATTERN
```

Search the current screen contents.  With `--wait`, polls once per second
until a match is found or the timeout (default 10 s) expires.  Exits 0 on
match, 1 on no-match/timeout.

```
mockterm send-keys [-s ID] [STRING | KEYNAME]...
```

Send input to the terminal.  Key names follow tmux conventions:
`Enter`, `Escape`, `C-c`, `Tab`, `Up`, `Down`, etc.

```
mockterm cat  [-s ID] [-e]
mockterm head [-s ID] [-e] [-n LINES]
mockterm tail [-s ID] [-e] [-n LINES]
```

Retrieve screen contents.  `-e` / `--escape-codes` preserves ANSI escape
codes (default: stripped).

```
mockterm kill [-s ID]
```

Kill a running session and remove it from `.mockterm`.

## OpenShell setup

### GitHub access

Create a GitHub Fine-Grained Personal Access Token with the following permissions
(restricted to this repository and/or your fork):

 * Pull Requests: Read and Write
 * Contents: Read and Write
 * Issues: Read and Write

and create a provider for it:

```sh
read GITHUB_TOKEN
# Paste in your token
export GITHUB_TOKEN
openshell provider create --name github-mockterm --type github --from-existing
```

### Build the custom sandbox container

```sh
podman build -t mockterm-sandbox:latest ./openshell
```

### Create the sandbox

```sh
$ openshell sandbox create --name mockterm  --provider github-mockterm --provider vertex-local --from=mockterm-sandbox:latest

Created sandbox:

sandbox@sandbox-mockterm:~$ gh repo clone owtaylor/mockterm
sandbox@sandbox-mockterm:~$ cd mockterm
```

```sh
Run your agent
```
