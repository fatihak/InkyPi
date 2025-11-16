document.addEventListener('DOMContentLoaded', function() {
    const imageContainer = document.querySelector('.image-container');
    const img = imageContainer.querySelector('img');
    let modalOverlay = null;
    let modalImg = null;
    let observer = null;
    
    if (!imageContainer || !img) return;

    // Handle click on image to show modal
    img.addEventListener('click', function(e) {
        e.stopPropagation();
        
        // Create overlay with image
        modalOverlay = document.createElement('div');
        modalOverlay.className = 'image-modal-overlay';
        
        modalImg = document.createElement('img');
        modalImg.src = img.src;
        modalOverlay.appendChild(modalImg);
        
        document.body.appendChild(modalOverlay);
        imageContainer.classList.add('maximized');
        document.body.style.overflow = 'hidden';
        
        // Observe original image for src changes
        observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.attributeName === 'src' && modalImg) {
                    modalImg.src = img.src;
                }
            });
        });
        
        observer.observe(img, { attributes: true, attributeFilter: ['src'] });
    });

    // Handle click on overlay to close modal
    document.addEventListener('click', function(e) {
        if (imageContainer.classList.contains('maximized') && modalOverlay && !img.contains(e.target)) {
            if (observer) {
                observer.disconnect();
                observer = null;
            }
            modalOverlay.remove();
            modalOverlay = null;
            modalImg = null;
            imageContainer.classList.remove('maximized');
            document.body.style.overflow = '';
        }
    });
});
