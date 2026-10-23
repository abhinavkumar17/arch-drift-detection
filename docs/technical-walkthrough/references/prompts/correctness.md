## CORR-1: Preserve intended behavior and data

Scope: Problems introduced or worsened by the change that produce an
incorrect result, inconsistent state, lost data, or a failed operation.
Timing, threading and lifecycle causes belong to CORR-2. Architecture
boundaries and preferred designs do not establish a correctness bug alone.

Avoid: Wrong identifiers or values, reversed conditions, inconsistent state
updates, and mishandling reachable null, empty, boundary or failure cases.

Prefer: Behavior consistent with the contracts demonstrated by relevant
callers and tests, checked against the implementation. This review input
does not include PR titles, descriptions or a separate requirements document.
Without stated requirements, treat a behavior change as unintended only
when relevant callers or tests contradict it. Otherwise record the missing
behavioral requirement as a limitation. Existing behavior alone does not
establish that a change is wrong.

Justifies a comment: Identify the triggering input or state, trace the
changed execution path, and explain the actual result versus the expected
result supported by caller or test evidence. A function name, imaginable
edge case, or missing test alone is insufficient. If callers and tests
conflict and available evidence does not resolve the conflict, record it
as a limitation rather than choosing a contract by assumption.

Illustrative examples reserved for instruction, not evaluation:
- An integer download-progress calculation newly divides by a total-byte value that
  an inspected caller uses as zero when size is unknown; that reachable
  input now throws instead of preserving the caller's unknown-size state.
- A pagination helper changes an exclusive upper bound to an inclusive one,
  contradicting inspected caller code that concatenates consecutive pages
  without overlap, so boundary items are duplicated.

Exceptions and boundaries:
- Different behavior alone is not a defect; establish the contradicted
  caller or test contract and the concrete consequence.
- Equivalent refactoring is not a defect when required behavior is preserved.
- Missing expected-behavior or reachability evidence remains a limitation.
- Examples illustrate reasoning, not an exhaustive list of detectable bugs.

## CORR-2: Respect lifecycle and concurrency

Scope: Problems introduced or worsened by the change whose cause is
threading, timing, cancellation or lifecycle ownership. A wrong result
independent of these factors belongs to CORR-1.

Avoid: Blocking I/O or heavy computation on the main thread; work with an
inappropriate lifetime; UI collection that remains active after its view
is destroyed; long-lived retention of an Activity, Fragment or View; and
concurrent read-modify-write operations that can lose shared-state updates.
GlobalScope, direct Flow collection or a context reference is a reason to
inspect ownership and consequences, not proof of a defect by itself.

Prefer: Work owned by an appropriate scope, including viewModelScope or a
lifecycle-aware UI scope; appropriate dispatching for blocking work; and
atomic updates or synchronization where concurrent state modification needs
it. StateFlow.update is suitable for updating one StateFlow value; it does
not make a multi-object operation atomic. UI collection should match the
lifetime of the UI consuming it.

Justifies a comment: Establish the relevant execution context and owner
from available code. For a race, show a possible interleaving; for a lifecycle
defect, identify the lifecycle event and surviving work or retained reference;
for main-thread blocking, identify the reachable blocking operation and its
main-thread call path. Explain the resulting freeze, lost update, leak,
crash or stale state. Do not require irrelevant evidence, such as a dispatcher
for a reference-retention defect.

Illustrative Android cases reserved for instruction, not evaluation:
- A Fragment starts a collector in its Fragment lifecycle scope and captures
  the current view binding; after onDestroyView, later emissions still access
  the old view because the Fragment itself remains alive.
- Two concurrent operations each read the same StateFlow counter and write
  an incremented value; a supported interleaving loses one increment.

Exceptions and boundaries:
- A suspend declaration alone does not move work off the main thread.
- Standard Room asynchronous DAO queries and Retrofit's native suspend
  network calls can be invoked from the main dispatcher. That invocation
  alone is not a defect. This does not establish main-safety for synchronous
  calls or custom blocking/computation code surrounding those operations.
- viewModelScope children are cancelled when the ViewModel is cleared;
  their use alone is not a leak. A ViewModel can outlive a particular view,
  and blocking or non-cooperative work may not stop promptly on cancellation.
- Work intentionally managed by an application-level or other longer-lived
  owner may legitimately survive a screen. Establish an ownership mismatch
  and concrete consequence before reporting it.
- A missing preferred API is not itself a bug: alternative lifecycle and
  synchronization mechanisms can be correct.
- If the ownership, execution context or interleaving needed to support a
  claim cannot be established, record the missing evidence as a limitation.
