P21-FIX-BUG: self._chain = chain if chain is not None else AuditChain()

Previous: chain or AuditChain() — empty chain (len=0) is falsy, so a freshly-created
chain passed to AuditLogger was silently replaced with a DEFAULT-secret chain.
Result: summary().genesis_hash and verify_chain() used wrong secret.

This file is the corrected version with 172/172 tests passing.