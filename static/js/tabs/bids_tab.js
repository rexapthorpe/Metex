// static/js/bids.js

document.addEventListener("DOMContentLoaded", function () {

  // Close modal on outside click
  window.addEventListener("click", function (e) {
    const modal = document.getElementById("editBidModal");
    if (e.target === modal) closeEditBidModal();
  });

  // Sidebar tab state (unrelated to modal)
  document.querySelectorAll(".account-sidebar a").forEach(link => {
    link.addEventListener("click", function () {
      const target = this.getAttribute("href").slice(1);
      localStorage.setItem("activeAccountTab", target);
    });
  });

  // Intercept the modal form submit
  document.addEventListener("submit", function (e) {
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

// Open the Edit Bid modal and load the form
function openEditBidModal(bidId) {
  const modal   = document.getElementById("editBidModal");
  const content = document.getElementById("editBidModalContent");
  if (!modal || !content) {
    return console.error("Modal container missing");
  }

  // Reset content & wizard
  content.innerHTML = "";
  
  fetch(`/bids/edit_form/${bidId}`, { cache: "no-store" })
    .then(resp => {
      if (!resp.ok) throw new Error(resp.statusText);
      return resp.text();
    })
    .then(html => {
      // Inject the partial
      content.innerHTML = html;
      // Initialize step 1
      goToStep(1);
      // Show the modal
      modal.style.display = "flex";
      modal.classList.add("active");
    })
    .catch(err => {
      console.error("❌ Fetch error:", err);
      content.innerHTML = '<p class="error-msg">Error loading form. Please try again.</p>';
      modal.style.display = "flex";
    });
}

// Close a bid via AJAX and remove its card from the DOM
function closeBid(bidId) {
  if (!confirm('Are you sure you want to close this bid?')) return;
  fetch(`/bids/cancel/${bidId}`, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  })
    .then(res => {
      if (res.ok) {
        // find and remove the bid-card
        const btn = document.querySelector(`button[onclick="closeBid(${bidId})"]`);
        if (btn) {
          const card = btn.closest('.bid-card');
          if (card) card.remove();
        }
      } else {
        alert('Failed to close bid.');
      }
    })
    .catch(() => alert('Something went wrong.'));
}
// expose globally for inline onclicks
window.closeBid = closeBid;


// Close the Edit Bid modal and clear its content
function closeEditBidModal() {
  const modal = document.getElementById("editBidModal");
  const content = document.getElementById("editBidModalContent");

  if (modal) {
    modal.style.display = "none";
    modal.classList.remove("active");
  }

  if (content) content.innerHTML = "";

  // Go back to the Bids tab
  showTab("bids");
}
