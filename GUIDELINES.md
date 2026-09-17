# Android Architecture Guidelines

Status: Initial draft agreed with Abhinav; awaiting Prateek's review.

These are the conventions selected for the sample Android application. They are not universal requirements for every Android project. The initial scope is Jetpack Compose screens using ViewModels. Legacy exceptions and iOS rules have not yet been defined.

## Rule 1: The ViewModel owns screen data

The ViewModel owns screen data and its associated loading and error states. Composables display that state and send user actions back through callbacks to the ViewModel. State flows down to the UI, and user actions flow back up.

Reusable composables can receive state and callbacks from their parent; they do not each need a ViewModel.

### Why

This separates screen data management from rendering and gives screen data one owner. The ViewModel delegates data access to the repository rather than implementing network or database access itself.

### Example that violates this rule

The composable loads and owns the product list instead of receiving it from the ViewModel.

```kotlin
@Composable
fun ProductsScreen(repository: ProductRepository) {
    var products by remember { mutableStateOf(emptyList<Product>()) }

    LaunchedEffect(Unit) {
        products = repository.loadProducts()
    }

    ProductList(products)
}
```

### Example that follows this rule

The ViewModel owns and loads the product list through the repository. Compose observes and displays it.

```kotlin
class ProductsViewModel(
    private val repository: ProductRepository
) : ViewModel() {
    private val _products = MutableStateFlow<List<Product>>(emptyList())
    val products = _products.asStateFlow()

    init {
        viewModelScope.launch {
            _products.value = repository.loadProducts()
        }
    }
}

@Composable
fun ProductsScreen(viewModel: ProductsViewModel) {
    val products by viewModel.products.collectAsStateWithLifecycle()
    ProductList(products)
}
```

These are simplified illustrative snippets, not a complete runnable application. Imports, supporting types, ViewModel creation, and loading/error handling are omitted to focus on ownership. In the complete implementation, loading and error states also belong to the ViewModel. User-action callbacks are described by the rule but not illustrated in this initial-load example.

### Allowed UI state

- Simple visual state used by one composable, such as whether a dropdown is open, may stay in that composable.
- When multiple composables need to read or change visual state, it can live in their nearest common parent or a UI state holder.
- State needed by business logic belongs in the ViewModel for this project's chosen architecture, such as a selected filter that determines which data is loaded.

Using `remember` or `LaunchedEffect` is not itself a violation. The issue in the first example is ownership of screen data and its loading, not the presence of those APIs.

### References

- [Android architecture recommendations](https://developer.android.com/topic/architecture/recommendations)
- [Where to hoist state](https://developer.android.com/develop/ui/compose/state-hoisting)

## Rule 2: ViewModels access data through repositories

ViewModels use repositories to access application data. They do not call network APIs, Retrofit services, or database DAOs directly. Repositories handle access to those data sources.

### Why

This keeps network and database details out of the ViewModel. A change in where data comes from can be handled behind the repository boundary, while the ViewModel remains focused on preparing screen state.

### Example that violates this rule

The ViewModel depends directly on a Retrofit service and calls it to load products.

```kotlin
class ProductsViewModel(
    private val api: ProductsApi // Retrofit service
) : ViewModel() {
    private val _products = MutableStateFlow<List<Product>>(emptyList())
    val products = _products.asStateFlow()

    fun refresh() {
        viewModelScope.launch {
            _products.value = api.getProducts()
        }
    }
}
```

The same boundary violation applies if the ViewModel calls a database DAO directly.

### Example that follows this rule

The ViewModel calls the repository. The repository delegates the request to the API.

```kotlin
class ProductRepository(
    private val api: ProductsApi
) {
    suspend fun loadProducts(): List<Product> = api.getProducts()
}

class ProductsViewModel(
    private val repository: ProductRepository
) : ViewModel() {
    private val _products = MutableStateFlow<List<Product>>(emptyList())
    val products = _products.asStateFlow()

    fun refresh() {
        viewModelScope.launch {
            _products.value = repository.loadProducts()
        }
    }
}
```

These snippets illustrate an alternative version of the product example, not additional classes to paste alongside Rule 1. Imports, dependency construction, and loading/error handling are omitted. For simplicity, the sample API returns `Product` values; it does not establish a rule about transport models or mapping.

### Review scope

The relevant difference is the dependency and call: a direct API or DAO dependency in the ViewModel violates this rule; the repository's API call does not. Repository interfaces, caching, and a separate use-case layer are not requirements established by this rule.

### Reference

- [Android architecture recommendations](https://developer.android.com/topic/architecture/recommendations)

## Rule 3: Expose read-only screen state and handle changes through actions

The ViewModel exposes its screen state through a read-only API. The UI observes that state and requests changes through ViewModel actions or callbacks. Mutable state holders remain private to the ViewModel; UI code does not assign to them directly.

This makes Rule 1's ownership boundary explicit. It applies to ViewModel-owned screen state, not the local visual state allowed by Rule 1.

### Why

Keeping state updates behind ViewModel actions provides one controlled place to coordinate screen-state changes and delegate business operations. The UI communicates what the user did instead of deciding how to update shared screen data.

### Example that violates this rule

The ViewModel exposes a mutable state holder, allowing UI code to overwrite the product list directly.

```kotlin
class ProductsViewModel : ViewModel() {
    val products = MutableStateFlow<List<Product>>(emptyList())
}

@Composable
fun ClearProductsButton(viewModel: ProductsViewModel) {
    Button(onClick = { viewModel.products.value = emptyList() }) {
        Text("Clear displayed products")
    }
}
```

Declaring the property with `val` does not make the state holder read-only: callers can still assign to its `value`.

### Example that follows this rule

The mutable holder is private. The UI sees a read-only state stream and requests the change through an action.

```kotlin
class ProductsViewModel : ViewModel() {
    private val _products = MutableStateFlow<List<Product>>(emptyList())
    val products: StateFlow<List<Product>> = _products.asStateFlow()

    fun clearDisplayedProducts() {
        _products.value = emptyList()
    }
}

@Composable
fun ClearProductsButton(viewModel: ProductsViewModel) {
    Button(onClick = viewModel::clearDisplayedProducts) {
        Text("Clear displayed products")
    }
}
```

These simplified snippets focus only on update access. Product loading, imports, and supporting types are omitted. Clearing the displayed list here does not delete stored products. Each example is an alternative, not a class to paste alongside the earlier examples.

### Review scope

Public mutable screen-state holders and direct UI writes to ViewModel-owned state violate this rule. Actions can be ordinary methods; a separate intent class or event framework is not required. Reusable composables may receive callbacks from their parent rather than a ViewModel directly.

A read-only state stream does not automatically make its contained objects immutable. Exposed screen-state values must also avoid mutable collections or properties that let the UI change ViewModel-owned data indirectly.

### Reference

- [Where to hoist state](https://developer.android.com/develop/ui/compose/state-hoisting)

## Rule 4: ViewModels receive dependencies instead of constructing them

ViewModels receive collaborators such as repositories through constructor parameters. A separate application setup layer creates and connects repositories and their data sources, and supplies them through a ViewModel factory or dependency-injection framework.

Manual dependency injection and framework-based injection are both allowed. This rule does not require a particular library or folder name.

### Why

Constructor parameters make dependencies explicit and let the application's setup control their creation and lifetime. The ViewModel can focus on preparing screen state rather than configuring its collaborators.

### Example that violates this rule

The ViewModel constructs its own repository and API client.

```kotlin
class ProductsViewModel : ViewModel() {
    private val repository = ProductRepository(
        api = createProductsApi()
    )
}
```

Here, `createProductsApi()` represents application-specific API-client construction. The ViewModel is responsible for assembling its data-access dependencies.

### Example that follows this rule

The ViewModel receives the repository from outside.

```kotlin
class ProductsViewModel(
    private val repository: ProductRepository
) : ViewModel() {
    // Screen-state logic uses the supplied repository.
}
```

Application setup constructs the API client and repository, then configures a ViewModel factory or injection framework to supply that repository. The screen obtains its ViewModel through the lifecycle-aware ViewModel mechanism rather than constructing a new ViewModel during recomposition.

These simplified snippets illustrate dependency ownership only. Factory/framework configuration and screen-state methods are omitted; a constructor parameter alone is not a complete dependency-injection setup.

### Review scope

Constructing repositories, API clients, or database dependencies inside the ViewModel violates this rule. Creating ordinary state values or other simple local values inside the ViewModel does not.

Injection does not change architectural responsibility: it does not justify injecting a direct API or DAO dependency that violates Rule 2, or placing screen-specific Activity, Fragment, or View references in a ViewModel. UI-specific objects remain with the UI.

## Rule 5: The data layer does not depend on the UI

Repositories and data sources return data or communicate failures without depending on ViewModels or UI components. They do not update a ViewModel directly, display UI messages, or trigger screen navigation. The ViewModel interprets results into screen state, and the UI handles presentation.

### Why

This keeps data access independent of any particular screen. The same repository can serve different callers without knowing how they display results or errors.

### Example that violates this rule

The repository receives a ViewModel and directly updates its screen state.

```kotlin
class ProductRepository(
    private val api: ProductsApi,
    private val screen: ProductsViewModel
) {
    suspend fun loadProducts() {
        val products = api.getProducts()
        screen.showProducts(products)
    }
}
```

Here, `showProducts` represents a screen-state update method. The repository knows about a presentation-layer class and controls it, reversing the intended dependency direction.

### Example that follows this rule

The repository returns products. The ViewModel calls it and updates its own state.

```kotlin
class ProductRepository(
    private val api: ProductsApi
) {
    suspend fun loadProducts(): List<Product> = api.getProducts()
}

class ProductsViewModel(
    private val repository: ProductRepository
) : ViewModel() {
    private val _products = MutableStateFlow<List<Product>>(emptyList())
    val products = _products.asStateFlow()

    fun refresh() {
        viewModelScope.launch {
            _products.value = repository.loadProducts()
        }
    }
}
```

These are simplified alternative examples. Imports, construction, and loading/error handling are omitted. Failures can be communicated to callers through exceptions or explicit result types; this rule does not select one error-handling mechanism. Neither mechanism should require the repository to control a screen.

### Review scope

Dependencies on ViewModels, Activities, Fragments, UI views, or screen-navigation controllers in repositories or data sources violate this boundary. Wrapping a UI command in a callback does not remove the violation if the data layer still decides to display a message or navigate.

Returning data, emitting data streams, and reporting failures are allowed. This rule does not ban all Android dependencies: an appropriately scoped application context used for storage or another platform data API can be legitimate. Using a context to show UI messages is a presentation responsibility and violates this rule.
