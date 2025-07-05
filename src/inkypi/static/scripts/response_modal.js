// Function to Show the Response Modal
function showResponseModal(status, message) {
    const modal = document.getElementById('responseModal');
    const modalContent = document.getElementById('modalContent');
    const modalMessage = document.getElementById('modalMessage');

    // Remove any previous status classes
    modal.classList.remove('success', 'failure');

    // Add the correct class based on the status
    if (status === 'success') {
        modal.classList.add('success'); // Apply success class
    } else {
        modal.classList.add('failure'); // Apply failure class
    }
    modalMessage.textContent = message;

    // Display Modal
    modal.style.display = 'block';

    // Auto-Close Modal After 10 Seconds
    setTimeout(() => closeResponseModal(), 10000);
}

// Function to Close the Modal
function closeResponseModal() {
    const modal = document.getElementById('responseModal');
    modal.style.display = 'none';
}
