// Toast notification shown at the top of the page (success or failure)
let responseModalTimer = null;

function showResponseModal(status, message) {
    const modal = document.getElementById('responseModal');
    const modalMessage = document.getElementById('modalMessage');
    if (!modal || !modalMessage) return;

    modal.classList.remove('success', 'failure');
    modal.classList.add(status === 'success' ? 'success' : 'failure');
    modal.setAttribute('role', status === 'success' ? 'status' : 'alert');
    modalMessage.textContent = message;
    modal.style.display = 'block';

    // Restart the auto-close timer so a newer message is not closed early
    clearTimeout(responseModalTimer);
    responseModalTimer = setTimeout(closeResponseModal, status === 'success' ? 5000 : 10000);
}

function closeResponseModal() {
    const modal = document.getElementById('responseModal');
    if (modal) modal.style.display = 'none';
}

// Show a message stored before a page reload/redirect (sessionStorage "storedMessage")
window.addEventListener('load', () => {
    let stored = null;
    try {
        stored = sessionStorage.getItem('storedMessage');
        sessionStorage.removeItem('storedMessage');
    } catch (e) { /* storage unavailable */ }
    if (stored) {
        try {
            const { type, text } = JSON.parse(stored);
            showResponseModal(type, text);
        } catch (e) { /* ignore malformed message */ }
    }
});

function storeMessageForNextPage(type, text) {
    try { sessionStorage.setItem('storedMessage', JSON.stringify({ type, text })); } catch (e) { /* ignore */ }
}
