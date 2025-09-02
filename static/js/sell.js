function toggleGradingService() {
    const graded = document.getElementById("graded").value;
    const serviceDiv = document.getElementById("grading-service-section");
    serviceDiv.style.display = graded === "1" ? "block" : "none";
}
