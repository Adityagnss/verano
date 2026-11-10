# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Report it privately with GitHub: open the repository's **Security** tab and choose **Report a vulnerability**.
Include what you found, the steps to reproduce it, and the version or commit you tested. We will confirm we
received it, tell you what we plan to do, and credit you when it is fixed if you want that.

## What is in scope

- The Verano backend, web app, command-line tool and SDKs in this repository.
- The default Docker Compose setup.

Examples: a way to read another organization's data, to run code outside the sandbox, to reach internal
addresses through "Test your own app", or to read a stored provider key.

## What is not in scope

- Problems that need an attacker who already controls the server or has an owner's password.
- Findings about a third-party provider's API.
- Running Verano with the development settings on the open internet. Production mode (`VERANO_ENVIRONMENT=production`)
  refuses the unsafe ones; see the [self-hosting guide](website/content/self-hosting.md).

## Good to know

- Provider keys are stored encrypted and are never shown again after they are saved.
- Custom checks written in Python run in a separate container with no internet, a read-only disk and limits.
  That container shares a network with the backend today, which is a known limit.
- The runtime screen for prompt injection and personal data catches obvious cases only. It is not a security boundary.
