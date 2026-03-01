# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in dictare, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please use one of the following methods:

1. **GitHub Security Advisory** (preferred): Use [GitHub's private vulnerability reporting](https://github.com/dragfly/dictare/security/advisories/new) to submit a report.

2. **Email**: Contact the maintainers directly (if contact info is available in the repository).

## What to Include

When reporting a vulnerability, please include:

- A description of the vulnerability
- Steps to reproduce the issue
- Potential impact
- Any suggested fixes (optional)

## Response Timeline

- We will acknowledge receipt within 48 hours
- We will provide an initial assessment within 7 days
- We will work with you to understand and resolve the issue

## Scope

This security policy applies to:

- The dictare Python package
- The install script (`install.sh`)
- Any official extensions or plugins

## Security Considerations

dictare handles:

- **Audio input**: Microphone access for speech-to-text
- **Keyboard simulation**: Injecting text into applications
- **Local model inference**: Running Whisper models locally

All processing happens locally on your machine. No audio or text is sent to external servers unless you explicitly configure an external LLM provider.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

We recommend always using the latest version.
