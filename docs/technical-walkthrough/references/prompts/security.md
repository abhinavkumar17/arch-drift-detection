## SEC-1: Preserve authentication and access control

Scope: Problems introduced or worsened by the change that let a caller act
without the required identity or permission, or access another user's or another app's
protected data or operations. Authentication establishes identity; authorization
determines
which operations and resources that identity may access. Ordinary incorrect
results without an access-control consequence belong to correctness.

Avoid: Removing or bypassing an established identity, ownership or permission
check; trusting caller-supplied identity as authority; exposing protected
operations through a newly reachable Android component without effective
access control; treating identity or account values from intent extras or
deep-link parameters as authority without verification; forwarding untrusted
Intents to startActivity or sendBroadcast without enforcing the intended
destination and capabilities; exposing mutable PendingIntents whose mutable
fields let another app perform an unauthorized operation; exposing privileged
WebView JavaScript interfaces to content the app does not control; allowing
a deep link to bypass confirmation or re-authentication required by the
established sensitive-action flow.

Prefer: Enforcement at the boundary that actually controls the protected
operation. Account for effective manifest permissions, caller checks and
downstream enforcement before concluding a check is missing.

Justifies a comment: Identify the caller, the protected operation or data,
the access rule supported by inspected code, and the changed reachable path
that violates it. Explain which effective protection is bypassed and the
unauthorized consequence. A suspicious API or removed UI check alone is
insufficient. Use bounded lookup to resolve a specific missing protection.

Illustrative Android case reserved for instruction, not evaluation:
- A previously internal service becomes externally reachable and can perform
  a protected local operation for another app; inspected manifest and handler
  code establish that no effective permission or caller check protects it.

Exceptions and boundaries:
- Exported components, public deep links and anonymous functionality can be
  intentional. Reachability alone is not a vulnerability.
- A hidden button or client-side navigation check is not evidence of server
  authorization. Missing server code does not prove that the server is unsafe.
- Do not request a duplicate check when an effective platform or downstream
  check already enforces the required boundary.
- Without PR requirements, establish the access contract from inspected code
  and tests; do not invent which roles or users should be allowed.
- If the relevant caller, access rule or enforcement cannot be established,
  record a limitation rather than an unverified security finding.
- Mutable PendingIntents and JavaScript interfaces are not defects solely
  because those APIs are used. Establish attacker control, the reachable
  capability and the effective platform or application protections.
- Respect the supported Android versions and actual configuration; do not
  assume a platform mitigation exists on every supported device.

## SEC-2: Protect sensitive data

Scope: Problems introduced or worsened by the change that expose credentials,
tokens or personal data to an unintended recipient through visible outputs, logs, storage,
transport or inter-app sharing. Access-control bypass belongs to SEC-1;
report the same underlying issue once using the shared base's selection rule.

Avoid: Emitting sensitive values into logs or telemetry; removing established
storage protection for secrets; storing secrets without protection required
by the evidenced exposure scenario; sending sensitive values over cleartext
connections; placing sensitive data in intents, clipboard or shared files
that unintended recipients can read.

Prefer: Omit or redact sensitive values from outputs; minimize retention;
use appropriate encryption with keys protected by Android Keystore when
needed; use TLS with effective certificate validation for sensitive transport;
limit sharing to intended recipients, data and lifetime. Keystore protects
cryptographic keys, not arbitrary application data directly.

Justifies a comment: Identify the sensitive value, trace the changed path
to its destination, and establish who can read it and under what conditions.
For storage, inspect applicable access, backup and sharing controls. For logs,
inspect build gating and the logging or telemetry destination. Show the
concrete exposure rather than inferring it from an API name alone.

Illustrative case reserved for instruction, not evaluation:
- A changed network interceptor logs complete request headers containing an
  Authorization token. Supplied build evidence establishes that the call is
  retained in the release variant, and inspected logging code uploads it to
  a telemetry recipient not authorized to receive credentials. The finding
  traces the token through that path, rather than flagging logging alone.

Exceptions and boundaries:
- Feature flags and ordinary display preferences are not secrets. An
  identifier may still be sensitive if it identifies a person or grants access;
  establish its meaning from code instead of treating all identifiers alike.
- Plain app-private SharedPreferences, files or databases are not automatically
  readable by other apps. Lack of application-level encryption alone does not
  establish exposure; identify the applicable threat or weakened protection.
- Confirmed removal from the release artifact rules out that release logging
  path, not exposure in every build. Debug builds may still handle real data
  or upload logs; do not assume either safe gating or exposure without evidence.
- Do not assume ordinary apps can read all logcat output or every clipboard
  entry; establish the relevant recipient and platform conditions.
- Intentional authorized sharing is not a defect simply because data leaves
  the app. Check the recipient and scope against the supported contract.
- If sensitivity or exposure cannot be established, record a limitation.
