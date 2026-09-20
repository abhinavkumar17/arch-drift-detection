# Android Architecture Guidelines — Version 2

These guidelines describe the design principles we want to follow and how they apply to our Android app. The examples help explain the intent; they aren’t the only acceptable way to write the code.

## 1. Keep screen logic separate from data access

A ViewModel manages what a screen needs to display. It asks for data and turns the result into screen state. It shouldn’t also need to understand how a network response is structured or how that data is stored.

For our app, repositories provide that separation. The ViewModel asks for products, and the repository takes care of obtaining them.

This follows **separation of concerns** and supports the **Single Responsibility Principle**: changes to how we fetch products and changes to how we display them should generally belong in different places.

### What we want to avoid

Here, the ViewModel calls the API and converts its response into products:

```kotlin
class ProductsViewModel(
    private val api: ProductsApi
) : ViewModel() {

    fun loadProducts() = viewModelScope.launch {
        val response = api.fetchProducts()
        val products = response.items.map { it.toProduct() }
        // Update screen state with products.
    }
}
```

The concern is that the ViewModel now knows about the network response. If that response changes, the screen’s ViewModel may need to change too.

Passing the API through the constructor helps with testing, but it doesn’t separate these responsibilities.

### What we prefer

The ViewModel asks a repository for products:

```kotlin
class ProductsViewModel(
    private val repository: ProductsRepository
) : ViewModel() {

    fun loadProducts() = viewModelScope.launch {
        val products = repository.loadProducts()
        // Update screen state with products.
    }
}
```

The network details stay behind the repository:

```kotlin
class NetworkProductsRepository(
    private val api: ProductsApi
) : ProductsRepository {

    override suspend fun loadProducts(): List<Product> =
        api.fetchProducts().items.map { it.toProduct() }
}
```

Now the ViewModel works with products without needing to know whether they came from an API, a database, or a cache. The repository can delegate those details to separate data sources as the application grows.

### What would justify a review comment?

A useful comment points to the code where data-access work has moved into the ViewModel and explains why that matters.

For example:

> This change makes the ViewModel interpret the API response directly. That ties screen logic to the network format. Keeping this conversion behind the repository would let the ViewModel continue working with products without knowing how they were fetched.

A class name alone doesn’t establish a problem. The reviewer needs enough surrounding code to understand what the dependency actually does. If that context is missing, the finding remains uncertain. Any agreed project exception also needs to be considered.

*These snippets are simplified illustrations. Imports, supporting types, error handling, and screen-state updates are omitted to keep the example focused.*

## 2. Depend on what a component provides, not how it is built

The ViewModel needs a way to get products. It shouldn’t need to know which networking library, database, or repository implementation provides them.

This follows the **Dependency Inversion Principle**: the screen’s logic depends on a contract, and the data implementation fulfills that contract.

### What we want to avoid

The ViewModel requires a specific network-backed repository:

```kotlin
class ProductsViewModel(
    private val repository: NetworkProductsRepository
) : ViewModel()
```

This keeps data access outside the ViewModel, satisfying our first guideline. But the ViewModel still depends on a particular implementation, making it harder to substitute another provider independently.

### What we prefer

A small interface describes what the ViewModel needs:

```kotlin
interface ProductsRepository {
    suspend fun loadProducts(): List<Product>
}

class ProductsViewModel(
    private val repository: ProductsRepository
) : ViewModel()
```

The network-backed implementation fulfills that contract:

```kotlin
class NetworkProductsRepository(
    private val api: ProductsApi
) : ProductsRepository {

    override suspend fun loadProducts(): List<Product> =
        api.fetchProducts().items.map { it.toProduct() }
}
```

Application setup supplies the implementation, either manually or through a dependency-injection framework. A test can supply a fake repository using the same interface.

### What would justify a review comment?

A useful finding shows where application logic has become tied to a replaceable implementation and explains the consequence.

For example:

> The ViewModel now requires the network-backed repository directly. Depending on the existing product repository interface would keep that implementation choice in application setup and allow tests to supply a fake.

This does **not** mean every class needs an interface. The boundary matters when implementation details should vary independently. The contract should also avoid exposing network-specific types, or those details would still leak into the ViewModel.

*These are simplified Kotlin illustrations.*

## 3. Give shared state a clear owner

When several parts of a screen use the same data, it should be clear who can change it. Otherwise, different parts can make conflicting updates or maintain copies that fall out of sync.

For our Android app, the ViewModel owns screen state such as the product list, loading status, and errors. The UI displays that state and asks the ViewModel to handle user actions.

### What we want to avoid

The ViewModel exposes state that the UI can overwrite:

```kotlin
class ProductsViewModel : ViewModel() {
    val products = MutableStateFlow<List<Product>>(emptyList())
}

// Inside a UI click callback:
viewModel.products.value = emptyList()
```

Now both the UI and ViewModel can change the product list directly. Decisions about when and why it changes can spread across the screen.

### What we prefer

The ViewModel exposes a read-only stream and provides an action for requesting a change:

```kotlin
class ProductsViewModel : ViewModel() {
    private val _products =
        MutableStateFlow<List<Product>>(emptyList())

    val products: StateFlow<List<Product>> =
        _products.asStateFlow()

    fun clearDisplayedProducts() {
        _products.value = emptyList()
    }
}

// Inside a UI click callback:
viewModel.clearDisplayedProducts()
```

The UI reports what the user wants to do. The ViewModel controls the update and can apply any relevant checks in one place.

Clearing the displayed list here does not delete stored products. Persistent data still belongs behind the repository.

### What would justify a review comment?

A useful finding identifies shared state that unrelated callers can change, or competing copies that can become inconsistent.

For example:

> This change lets the screen overwrite the product list directly. Keeping updates inside the ViewModel would give the list one owner and prevent screen code from bypassing its update logic.

This does **not** mean all state belongs in a ViewModel. A dropdown’s expanded state can stay in the UI. Visual state shared by several composables can belong to their common parent or a dedicated UI state holder.

A read-only stream also doesn’t make its contents deeply immutable; exposing mutable objects could still allow changes outside the owner.

*These are simplified Kotlin illustrations. Imports, state collection, and loading/error handling are omitted.*
