$(document).ready(function () {
    // Restore search form values from session storage
    $('#search_query').val(sessionStorage.getItem('search_query') || '');
    $('#search_name').val(sessionStorage.getItem('search_name') || '');
    $('#category').val(sessionStorage.getItem('category') || '');

    let currentPage = 1;
    let resultsPerPage = 10; // Assume 10 results per page

    // Use the Mapbox token provided by the server
    mapboxgl.accessToken = window.mapboxToken;

    let map = new mapboxgl.Map({
        container: "map", // container ID
        style: "mapbox://styles/mapbox/light-v10", // style URL
        center: [-78.6821, 35.7847], // starting position [lng, lat]
        zoom: 12, // starting zoom
    });

    let markers = [];
    let allCategories = [];
    let bounds = new mapboxgl.LngLatBounds(); // Initialize bounds object

    function loadCategories() {
        $.ajax({
            url: "/categories",
            type: "GET",
            success: function (response) {
                allCategories = response;
                updateCategoryDropdown();
            },
            error: function (xhr, status, error) {
                console.error(
                    "An error occurred while loading the categories:",
                    error
                );
            },
        });
    }

    function updateCategoryDropdown(selectedCategory = "") {
        let categorySelect = $("#category");
        categorySelect.empty();
        categorySelect.append('<option value="">All Categories</option>');
        allCategories.forEach(function (category) {
            let selected = category === selectedCategory ? "selected" : "";
            categorySelect.append(
                `<option value="${category}" ${selected}>${category}</option>`
            );
        });
    }

    function loadResults(page) {
        let searchQuery = $("#search_query").val();
        let searchName = $("#search_name").val();

        let formData = $("#search-form").serialize();
        formData += `&page=${page}`;
        formData += `&category=${$("#category").val()}`;

        $.ajax({
            url: "/search",
            type: "POST",
            data: formData,
            success: function (response) {
                if (response.message) {
                    $("#results").html(
                        `<div class="alert alert-info">${response.message}</div>`
                    );
                    $("#pagination").empty();
                    markers.forEach((marker) => marker.remove()); // Clear existing markers
                    markers = [];
                    $("#category-container").hide();
                } else {
                    let resultsHtml =
                        '<div class="search-results-header">Search Results</div>';
                    markers.forEach((marker) => marker.remove()); // Clear existing markers
                    markers = [];
                    bounds = new mapboxgl.LngLatBounds(); // Reset bounds

                    let startIndex = (page - 1) * resultsPerPage;
                    let defaultImageUrl = "https://via.placeholder.com/100"; // Default image URL

                    response.data.forEach((item, index) => {
                        let serialNumber = startIndex + index + 1;
                        let imageUrl = item["image_url"]
                            ? item["image_url"]
                            : defaultImageUrl;

                        resultsHtml += `
                            <div class="list-group-item list-group-item-action" id="item-${index}">
                                <div style="display: flex; align-items: center;">
                                    <img src="${imageUrl}" alt="${item["name"]}">
                                    <div>
                                        <span class="marker-number">${serialNumber}.</span>
                                        <a href="/restaurant/${item["HSISID"]}" class="d-inline">${item["name"]}</a>
                                        <p class="mb-1">${item["address1"]}</p>
                                        <p class="mb-1">${item["city"]}</p>
                                        <p class="mb-1">${item["state"]}</p>
                                        <small>Phone: ${item["display_phone"]} | Zip: ${item["zip_code"]}</small>
                                    </div>
                                </div>
                                <div class="score-box">
                                    <span>${item["SCORE"]}</span>
                                </div>
                            </div>
                        `;

                        let marker = new mapboxgl.Marker()
                            .setLngLat([item["longitude"], item["latitude"]])
                            .setPopup(
                                new mapboxgl.Popup({ offset: 25 }) // add popups
                                    .setHTML(
                                        `<b>${serialNumber}. ${item["name"]}</b><br>${item["address1"]}<br>${item["city"]}, ${item["state"]}<br>Phone: ${item["display_phone"]}`
                                    )
                            )
                            .addTo(map);

                        markers.push(marker);

                        // Extend bounds to include each marker
                        bounds.extend([item["longitude"], item["latitude"]]);
                    });

                    // Fit map to the bounds of the markers
                    map.fitBounds(bounds, { padding: 50 });

                    $("#results").html(resultsHtml);

                    // Pagination
                    let paginationHtml = "";
                    for (let i = 1; i <= response.total_pages; i++) {
                        paginationHtml += `<li class="page-item ${
                            i === page ? "active" : ""
                        }"><a class="page-link" href="#">${i}</a></li>`;
                    }
                    $("#pagination").html(paginationHtml);

                    // Attach click event to pagination links
                    $("#pagination .page-link").click(function (e) {
                        e.preventDefault();
                        let selectedPage = parseInt($(this).text());
                        loadResults(selectedPage);
                    });

                    // Update categories dynamically based on filtered data
                    allCategories = response.categories;
                    updateCategoryDropdown($("#category").val());
                    $("#category-container").show();

                    // Update previous search values
                    previousSearchQuery = searchQuery;
                    previousSearchName = searchName;
                }
            },
            error: function (xhr, status, error) {
                console.error(
                    "An error occurred while loading the results:",
                    error
                );
            },
        });
    }

    $("#search-form").submit(function (e) {
        e.preventDefault();
        loadResults(1); // Load first page of results
    });

    $("#category").change(function () {
        loadResults(1); // Load first page of results when category changes
    });

    // Initial load
    $("#category-container").hide();
    loadCategories();
});
