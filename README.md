# mockterm

Mockterm is a command line utility that is designed to let an autonomous AI agent
to test changes to TUI programs by providing a headless terminal.

## Instructions for agents how to use mockterm

The `mockterm` command is present in your environment, and can be used to test interactive
TUI programs.

Usage:

```
mockterm start [-s ID] [--size=<COLS>x<ROWS>] <COMMAND> <ARG>...
```

Start a command, write session ID to .mockterm. Optionally name sessions, otherwise any running is killed and replaced.

```
mockterm grep [-s ID] [--wait] [-t <TIMEOUT>] [-<NUM>] [-A <NUM>] [-B <NUM>] [-C <NUM>] [PATTERN]
```

Search for a string in the current screen contents and output the result, optionally repeatedly
retrying until a match occurs.


```
mockterm send-keys [-s ID] [STRING | KEYNAME]...
```

Send input to the terminal. Key naming is like tmux send-keys [Enter/Escape/C-c]

```
mockterm cat
mockterm head [-n LINES]
mockterm tail [-n LINES]
```

Retrieve some portion of the current screen contents

## OpenShell setup

### GitHub access

Create a GitHub Fine-Grained Personal Access Token with the following permissions
(restricted to this repository and/or your fork):

 * Pull Requests: Set to Read and Write
 * Contents: Set to Read and Write
 * Issues: Set to Read and Write

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
