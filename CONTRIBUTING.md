# Contributing to Agentorium

> **中文说明**：这份写的是「改动怎么提交」——**不带密钥、不带私人稿子**；
> 上游的版权声明要保留；提 PR 时说清对用户看得见的影响。

Contributions are welcome through issues and pull requests.

Before submitting a change:

1. Do not include API keys, `.env` files, local `config.json`, private manuscripts
   or generated environments.
2. This project is a derivative of [xiauho/novalist](https://github.com/xiauho/novalist)
   (MIT License). Keep the upstream copyright notice in `LICENSE` intact, and keep
   references to upstream, to Claude Code, and to any model provider factual and
   compatibility-only — do not imply official authorization or endorsement.
3. Run `python -m unittest discover -s tests`.
4. Run `python -m compileall -q main.py core ui`.
5. Explain user-visible behavior and privacy effects in the pull request.

By contributing, you agree that your contribution may be distributed under the
project's MIT License and confirm that you have the right to submit it.
