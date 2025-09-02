// static/js/modals/edit_bid_modal.js
'use strict';

document.addEventListener("DOMContentLoaded", function() {
  // Close modal on outside click
  window.addEventListener("click", function(e) {
    const modal = document.getElementById("editBidModal");
    if (e.target === modal) closeEditBidModal();
  });

  // Intercept the modal form submit
  document.addEventListener("submit", function(e) {
    const form = e.target;
    if (form.id === "bid-form" && form.closest("#editBidModal")) {
      e.preventDefault();

      // remove old errors
      document.querySelectorAll(".error-msg").forEach(el => el.remove());

      const formData = new FormData(form);
      fetch(form.action, {
        method: "POST",
        body: formData
      })
      .then(res => res.json())
      .then(data => {
        if (!data.success) {
          // show validation errors
          if (data.errors) {
            Object.entries(data.errors).forEach(([name, msg]) => {
              const input = form.querySelector(`[name="${name}"]`);
              if (input) {
                const err = document.createElement("p");
                err.className = "error-msg";
                err.textContent = msg;
                input.insertAdjacentElement("afterend", err);
              }
            });
          } else {
            alert(data.message || "Something went wrong.");
          }
          return;
        }

        // success: close and refresh
        alert("✅ " + data.message);
        closeEditBidModal();
        location.reload();
      })
      .catch(err => {
        console.error("Form submission failed:", err);
        alert("Server error occurred.");
      });
    }
  });
});

/**
 * Opens the Edit Bid modal and loads the form
 */
function openEditBidModal(bidId) {
  const modal   = document.getElementById("editBidModal");
  const content = document.getElementById("editBidModalContent");
  if (!modal || !content) {
    return console.error("Modal container missing");
  }

  // Reset content
  content.innerHTML = "";

  fetch(`/bids/edit_form/${bidId}`, { cache: "no-store" })
    .then(resp => {
      if (!resp.ok) throw new Error(resp.statusText);
      return resp.text();
    })
    .then(html => {
      content.innerHTML = html;
      goToStep(1);
      modal.style.display = "flex";
      modal.classList.add("active");
    })
    .catch(err => {
      console.error("❌ Fetch error:", err);
      content.innerHTML = '<p class="error-msg">Error loading form. Please try again.</p>';
      modal.style.display = "flex";
    });
}

/**
 * Close the Edit Bid modal and clear its content
 */
function closeEditBidModal() {
  const modal   = document.getElementById("editBidModal");
  const content = document.getElementById("editBidModalContent");

  if (modal) {
    modal.style.display = "none";
    modal.classList.remove("active");
  }
  if (content) content.innerHTML = "";

  // Return to Bids tab
  if (typeof showTab === 'function') showTab("bids");
}

// Expose globally for inline handlers if needed
window.openEditBidModal = openEditBidModal;
window.closeEditBidModal = closeEditBidModal;
