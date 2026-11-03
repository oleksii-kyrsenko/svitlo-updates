#!/usr/bin/env python3
"""Verify the app's public intermediate and record strict official TLS evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import ssl
import subprocess
import tempfile

HOST = 'cabinet.cherkasyoblenergo.com'
PIN = '8c54c334b66ba4e426772af4a3f9136c19a1aec729fdb28c535c07a5a4ef22e0'
CERTIFICATE = Path(__file__).parent / 'certificates/sectigo-dv-r36.pem'


def run(args, **kwargs):
    return subprocess.run(['openssl', *args], capture_output=True, timeout=30, **kwargs)


def verify_intermediate():
    der = ssl.PEM_cert_to_DER_cert(CERTIFICATE.read_text())
    if hashlib.sha256(der).hexdigest() != PIN:
        raise RuntimeError('public_intermediate_fingerprint_mismatch')
    result = run(['verify', '-CApath', '/etc/ssl/certs', str(CERTIFICATE)])
    if result.returncode:
        raise RuntimeError('public_intermediate_not_verified_by_system_roots')
    return {'derSha256': PIN, 'systemRootVerification': True}


def capture(folder):
    report = {'schemaVersion': 1, 'host': HOST, 'intermediate': verify_intermediate(),
              'hostnameVerification': True, 'tlsVerificationDisabled': False,
              'observations': []}
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cherkasy-public-trust-') as temp:
        trust = Path(temp) / 'system-and-intermediate.pem'
        trust.write_bytes(Path('/etc/ssl/certs/ca-certificates.crt').read_bytes() + b'\n' + CERTIFICATE.read_bytes())
        for mode, ca_file in [('system', '/etc/ssl/certs/ca-certificates.crt'),
                              ('system-and-verified-intermediate', str(trust))]:
            args = ['s_client', '-connect', HOST + ':443', '-servername', HOST,
                    '-showcerts', '-verify_return_error', '-verify_hostname', HOST,
                    '-CAfile', ca_file]
            observation = {'mode': mode}
            try:
                reply = run(args, input=b'')
                raw = reply.stdout + b'\n' + reply.stderr
                observation['exitCode'] = reply.returncode
                # Persist public certificates only, never TLS session keys/tickets.
                certificates = re.findall(b'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', raw, re.S)
                observation['certificates'] = []
                for number, certificate in enumerate(certificates):
                    name = mode + '-' + str(number) + '.pem'
                    certificate += b'\n'
                    (folder / name).write_bytes(certificate)
                    der = ssl.PEM_cert_to_DER_cert(certificate.decode())
                    parsed = run(['x509', '-noout', '-subject', '-issuer', '-dates', '-ext', 'subjectAltName'], input=certificate)
                    observation['certificates'].append({'file': name, 'derSha256': hashlib.sha256(der).hexdigest(),
                                                        'metadata': parsed.stdout.decode().splitlines()})
                match = re.search(rb'Verify return code: (\d+)', raw)
                observation['verifyReturnCode'] = int(match[1]) if match else None
                observation['verificationErrors'] = [int(code) for code in re.findall(rb'verify error:num=(\d+):', raw)]
                observation['verified'] = reply.returncode == 0 and observation['verifyReturnCode'] == 0
            except subprocess.TimeoutExpired:
                observation['error'] = 'official_tls_diagnostic_timeout'
            report['observations'].append(observation)
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.out:
        report = capture(args.out)
        print(json.dumps({'host': HOST, 'intermediate': report['intermediate'],
                          'observations': [{k: v for k, v in item.items() if k != 'certificates'}
                                           for item in report['observations']]}))
    else:
        print(json.dumps(verify_intermediate()))
