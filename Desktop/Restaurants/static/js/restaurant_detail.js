$(document).ready(function () {
    const ctx = document.getElementById('inspectionChart').getContext('2d');

    const inspectionDates = JSON.parse(document.getElementById('inspection-dropdown').dataset.inspectionDates || '[]');
    const inspectionScores = JSON.parse(document.getElementById('inspection-dropdown').dataset.inspectionScores || '[]');
    const HSISID = document.getElementById('restaurant-detail').dataset.hsisid;

    const inspectionChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: inspectionDates,
            datasets: [{
                label: 'Inspection Scores',
                data: inspectionScores,
                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `Date: ${context.label}, Score: ${context.raw}`;
                        }
                    }
                }
            }
        }
    });

    if (inspectionDates.length > 0) {
        const latestDate = inspectionDates[0];
        $('#inspection-dropdown').val(latestDate).trigger('change');
        loadInspectionDetails(latestDate);
    }

    $('#inspection-dropdown').on('change', function() {
        const selectedDate = $(this).val();
        if (selectedDate) {
            loadInspectionDetails(selectedDate);
        }
    });

    function loadInspectionDetails(selectedDate) {
        $.ajax({
            type: 'POST',
            url: '/get_inspection_details',
            data: {
                HSISID: HSISID,
                inspect_date: selectedDate
            },
            success: function(response) {
                $('#violation-count').text(response.violation_count);
                const tableBody = $('#violation-table-body');
                tableBody.empty();

                if (response.violation_details && Array.isArray(response.violation_details)) {
                    response.violation_details.forEach(function(detail) {
                        if (detail.CRITICAL && detail.CATEGORY && detail.COMMENTS) {
                            const row = `<tr>
                                <td>${detail.CRITICAL}</td>
                                <td>${detail.CATEGORY}</td>
                                <td>${detail.COMMENTS}</td>
                            </tr>`;
                            tableBody.append(row);
                        }
                    });
                }

                $('#inspection-details').show();
            },
            error: function(error) {
                console.error("An error occurred:", error);
            }
        });
    }

    // Back to Search functionality with session storage
    document.getElementById('back-to-search').addEventListener('click', function (e) {
        e.preventDefault();

        // Store search form values in session storage
        sessionStorage.setItem('search_query', sessionStorage.getItem('search_query') || '');
        sessionStorage.setItem('search_name', sessionStorage.getItem('search_name') || '');
        sessionStorage.setItem('category', sessionStorage.getItem('category') || '');

        window.history.back();
    });
});
