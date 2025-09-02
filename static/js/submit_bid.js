function toggleGraderDropdown() {
    const requiresGrading = document.getElementById('requires_grading').value;
    const graderSection = document.getElementById('grader_dropdown_section');

    if (requiresGrading === 'yes') {
        graderSection.style.display = 'block';
    } else {
        graderSection.style.display = 'none';
        document.getElementById('preferred_grader').value = '';
    }
}

function setBidPrice(price) {
    const input = document.querySelector('input[name="bid_price"]');
    if (input) {
        input.value = price.toFixed(2);  // set the price with 2 decimal places
    }
}

function goToStep(stepNumber) {
    const steps = document.querySelectorAll('.step-panel');
    steps.forEach((panel, index) => {
        panel.style.display = (index === stepNumber - 1) ? 'block' : 'none';
    });
}




window.addEventListener('DOMContentLoaded', () => {
    toggleGraderDropdown(); // Pre-show dropdown if editing an existing graded bid
});
