# Application Protocol & Logging Specification

## 1. Message Types & JSON Wire Format

All communication between client and server uses UTF-8 encoded JSON objects terminated by a newline (`\n`).

### LOGIN (Client -> Server)