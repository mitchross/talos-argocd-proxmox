# Contributing to Sidero Omni + Talos + Proxmox Starter Kit

Thank you for considering contributing to this project! This starter kit is community-driven and welcomes contributions of all kinds.

## How to Contribute

### Reporting Issues

Found a bug or have a suggestion? Please [open an issue](../../issues) with:

- **Clear title** - Describe the issue concisely
- **Description** - Provide details about the problem or suggestion
- **Environment** - Include versions (Omni, Talos, Proxmox)
- **Steps to reproduce** - How can we recreate the issue?
- **Expected behavior** - What should happen?
- **Actual behavior** - What actually happens?
- **Logs** - Relevant log excerpts (sanitize any secrets!)

### Suggesting Enhancements

Have an idea to improve the starter kit? Great! Please:

1. Check if a similar issue already exists
2. Open a new issue with the "enhancement" label
3. Describe your use case and proposed solution
4. Be open to discussion and feedback

### Documentation Improvements

Documentation is crucial! Contributions include:

- Fixing typos or unclear explanations
- Adding examples or clarifications
- Improving troubleshooting guides
- Translating documentation
- Adding diagrams or illustrations

### Code Contributions

#### Setting Up Development Environment

1. **Fork the repository**
2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/sidero-omni-talos-proxmox-starter.git
   cd sidero-omni-talos-proxmox-starter
   ```
3. **Create a branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

#### Making Changes

**For documentation**:
- Use clear, concise language
- Include code examples where helpful
- Test commands and configurations
- Update table of contents if adding sections

**For configuration files**:
- Use `.example` suffix for templates
- Include inline comments explaining options
- Provide sensible defaults
- Document any required vs optional fields

**For scripts**:
- Add error handling
- Include usage instructions
- Use descriptive variable names
- Add comments for complex logic

#### Testing Your Changes

Before submitting:

1. **Test configurations**:
   - Verify example files have correct syntax
   - Test any scripts you've added or modified
   - Ensure commands work as documented

2. **Check documentation**:
   - Proofread for typos and clarity
   - Verify links work
   - Test code blocks in a clean environment

3. **Validate against .gitignore**:
   - Ensure no secrets are committed
   - Check that example files are included

#### Submitting a Pull Request

1. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: add support for X" # or "fix:", "docs:", etc.
   ```

2. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

3. **Open a Pull Request**:
   - Go to the original repository
   - Click "New Pull Request"
   - Select your branch
   - Fill out the PR template

4. **PR Guidelines**:
   - **Title**: Use conventional commit format
     - `feat:` for new features
     - `fix:` for bug fixes
     - `docs:` for documentation
     - `chore:` for maintenance
   - **Description**: Explain what and why
   - **Link issues**: Reference related issues
   - **Testing**: Describe how you tested
   - **Screenshots**: Include if relevant

## Commit Message Conventions

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): subject

body

footer
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Formatting, missing semi-colons, etc.
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance tasks

**Examples**:
```
feat(proxmox): add support for multiple disk configuration

Add configuration option to specify additional disks for VMs.
This allows separating OS disk from data disk.

Closes #42

---

docs(gpu): clarify extension installation process

Improve explanation of the two approaches for loading GPU extensions
based on feedback from Sidero Labs team.

---

fix(omni): correct SSL certificate path in example

The example pointed to wrong certificate location.
Fixed to use standard Let's Encrypt path.
```

## Code Style

### Shell Scripts
- Use `#!/bin/bash` shebang
- Enable error checking: `set -euo pipefail`
- Use descriptive variable names
- Quote variables: `"$VARIABLE"`
- Include usage/help functions
- Add error messages for failures

### YAML
- Use 2-space indentation
- Include inline comments for clarity
- Group related settings
- Use meaningful key names

### Markdown
- Use ATX-style headers (`#` not `===`)
- Include code block language specifiers
- Use relative links within repo
- Keep line length reasonable (100-120 chars)

## What We're Looking For

### High Priority
- Bug fixes and corrections
- Improved error messages
- Additional troubleshooting scenarios
- Real-world usage examples
- Documentation improvements

### Feature Ideas
- Alternative authentication providers (beyond Auth0)
- Additional machine class examples
- Monitoring/observability setup
- Backup/restore procedures
- High availability configurations
- Multi-disk VM support (when available in provider)
- Alternative DNS providers (beyond Cloudflare)

### Future Considerations
- Terraform modules for infrastructure
- Ansible playbooks for host setup
- CI/CD pipeline examples
- Cost optimization guides
- Security hardening guides

## Community Guidelines

### Be Respectful
- Be welcoming to newcomers
- Assume good intentions
- Provide constructive feedback
- Respect different perspectives
- Keep discussions on-topic

### Be Helpful
- Answer questions when you can
- Share your experience
- Provide context for decisions
- Link to relevant resources
- Help test PRs and issues

### Be Patient
- This is a community project
- Maintainers are volunteers
- Reviews take time
- Not all suggestions will be accepted

## Recognition

Contributors will be:
- Listed in commit history
- Mentioned in release notes (for significant contributions)
- Part of a growing community improving Kubernetes infrastructure

## Questions?

Not sure about something? Have questions?

- Open an issue with the "question" label
- Join [Sidero Labs Slack](https://slack.dev.talos-systems.io/)
- Check existing issues and PRs
- Review the documentation

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (see LICENSE file).

## Attribution

This starter kit builds upon:
- [Sidero Omni](https://github.com/siderolabs/omni)
- [Talos Linux](https://github.com/siderolabs/talos)
- [Omni Proxmox Provider](https://github.com/siderolabs/omni-infra-provider-proxmox)

Special thanks to the Sidero Labs team for their support and excellent tooling.

---

Thank you for contributing to making Kubernetes infrastructure management easier for everyone! 🚀
