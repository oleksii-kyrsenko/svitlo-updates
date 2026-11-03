The public Sectigo Public Server Authentication CA DV R36 intermediate is the
same certificate bundled in the Android application for the incomplete TLS chain
at `cabinet.cherkasyoblenergo.com`. It is valid through21March2036.

DER SHA256: `8c54c334b66ba4e426772af4a3f9136c19a1aec729fdb28c535c07a5a4ef22e0`.
Original public distribution URL:
`http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt`.
The certificate's authenticity is established cryptographically through the
runner's system Sectigo R46 root, not through the distribution URL's transport.

`verify-cherkasy-source-trust.py` requires the exact fingerprint and a successful
OpenSSL verification against system roots before the workflow supplies this
missing intermediate to Playwright's Node HTTP client using `NODE_EXTRA_CA_CERTS`.
TLS and hostname verification remain enabled. The source-only probe records
strict connection checks both with system certificates and with the intermediate;
it retains public certificates and verification results, never TLS session keys.
