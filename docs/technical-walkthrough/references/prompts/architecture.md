## ARCH-1: Keep screen logic separate from data access

Principle: Separation of concerns and Single Responsibility Principle.

Scope: Changes that make a ViewModel or other screen-logic class perform or
interpret data access directly, so screen logic depends on network response
formats, storage details or data-source choice. Repositories provide this
separation in this app. Incorrect behavior alone does not establish an architecture violation; this
principle requires evidence of a boundary violation.

Avoid: Calling an API, database or data source directly from a ViewModel;
mapping network or storage response types into domain models inside a
ViewModel; making screen logic depend on response structure.

    // ViewModel interprets the network response itself
    val products = api.fetchProducts().items.map { it.toProduct() }

Prefer: The ViewModel asks a repository for domain data and turns the result
into screen state. The repository, or data sources behind it, own fetching,
mapping and storage. Constructor injection of an API aids testing but does
not by itself separate these responsibilities.

    val products = repository.loadProducts()

Justifies a comment: Identify the changed line where data-access work entered
screen logic, the data-access detail it now depends on, and the consequence,
such as a response-format change forcing a ViewModel change.

Exceptions and boundaries:
- A class or dependency name alone does not establish a problem. Establish
  what the dependency actually does from inspected code; if that cannot be
  established, record a limitation.

## ARCH-2: Depend on what a component provides, not how it is built

Principle: Dependency Inversion Principle.

Scope: Changes that tie application logic to a specific replaceable
implementation where an existing or warranted contract should be used.

Avoid: Requiring, constructing or casting to a concrete implementation
(for example a network-backed repository) where application logic only
needs the contract it provides; contracts that expose network- or
storage-specific types.

    class ProductsViewModel(
        private val repository: NetworkProductsRepository
    ) : ViewModel()

Prefer: Depend on a small interface describing what the caller needs.
Application setup or dependency injection supplies the implementation, and
tests can supply a fake through the same interface.

    class ProductsViewModel(
        private val repository: ProductsRepository
    ) : ViewModel()

Justifies a comment: Identify the changed line that binds logic to a
concrete implementation, the existing or appropriate contract, and the
consequence for substitution or testing.

Exceptions and boundaries:
- Not every class needs an interface. Establish why the implementation
  should vary independently, for example multiple implementations, a test
  substitution boundary, or an existing contract the change bypasses.
- Wiring a concrete implementation in application setup or DI modules is
  expected, not a violation.

## ARCH-3: Give shared state a clear owner

Scope: Changes that let several callers modify the same state, or create
competing copies of state that can fall out of sync. The ViewModel owns
screen state such as content, loading status and errors; the UI displays it
and reports user actions.

Avoid: Exposing mutable state (for example a public MutableStateFlow) that UI
code can overwrite; UI code assigning ViewModel-owned state directly;
duplicating owned state in a second holder that is updated separately.

    // UI click callback
    viewModel.products.value = emptyList()

Prefer: The owner exposes read-only state and an action that requests the
change, so update decisions stay in one place.

    val products: StateFlow<List<Product>> = _products.asStateFlow()
    fun clearDisplayedProducts() { _products.value = emptyList() }

Justifies a comment: Identify the shared state, its intended owner, and the
changed line that lets another caller change it or creates a competing copy.
Explain which update logic is bypassed or what can become inconsistent.

Exceptions and boundaries:
- Not all state belongs in a ViewModel. Purely local UI state, such as a
  dropdown's expanded flag, can stay in the UI. Visual state shared by
  several composables can belong to their common parent or a UI state holder.
- A read-only stream does not make its contents deeply immutable; exposing
  mutable objects through it can still allow changes outside the owner.
- Clearing displayed state is not deleting stored data; persistent data
  remains behind the repository.
