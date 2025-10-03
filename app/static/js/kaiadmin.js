/**
 * Kaiadmin Lite JavaScript
 * Handles sidebar, responsive behavior, and other UI interactions
 */
document.addEventListener('DOMContentLoaded', function() {
    // Sidebar toggle for mobile
    const toggleSidebar = document.querySelector('.toggle-sidebar');
    const sidebarToggleBtn = document.getElementById('toggle-sidebar');
    const sidebar = document.querySelector('.sidebar');

    if (toggleSidebar) {
        toggleSidebar.addEventListener('click', function() {
            sidebar.classList.toggle('open');
        });
    }

    // Sidebar collapse functionality - Skip if already handled in base.html
    // The base.html template already handles the toggle-sidebar button
    // So we only set up the event if the element doesn't already have a listener
    if (sidebarToggleBtn && !sidebarToggleBtn.hasAttribute('data-listener-attached')) {
        // Mark that we're attaching a listener to avoid duplicates
        sidebarToggleBtn.setAttribute('data-listener-attached', 'true');
    }
    
    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', function(event) {
        if (window.innerWidth < 992 && 
            sidebar && 
            sidebar.classList.contains('open') && 
            !sidebar.contains(event.target) && 
            !toggleSidebar.contains(event.target)) {
            sidebar.classList.remove('open');
        }
    });
    
    // Handle window resize
    window.addEventListener('resize', function() {
        if (window.innerWidth >= 992 && sidebar && sidebar.classList.contains('open')) {
            sidebar.classList.remove('open');
        }
    });
    
    // Initialize tooltips if Bootstrap is available
    if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function(tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
    
    // Initialize popovers if Bootstrap is available
    if (typeof bootstrap !== 'undefined' && bootstrap.Popover) {
        const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
        popoverTriggerList.map(function(popoverTriggerEl) {
            return new bootstrap.Popover(popoverTriggerEl);
        });
    }
    
    // Add active class to nav items based on current page
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-link');
    
    navLinks.forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.parentElement.classList.add('active');
        }
    });
    
    // Handle card actions (minimize, maximize, close)
    const cardActions = document.querySelectorAll('.card-action');
    
    cardActions.forEach(action => {
        action.addEventListener('click', function(e) {
            e.preventDefault();
            const card = this.closest('.card');
            
            if (this.classList.contains('card-minimize')) {
                const cardBody = card.querySelector('.card-body');
                if (cardBody) {
                    cardBody.classList.toggle('d-none');
                    this.querySelector('i').classList.toggle('fa-minus');
                    this.querySelector('i').classList.toggle('fa-plus');
                }
            }
            
            if (this.classList.contains('card-maximize')) {
                card.classList.toggle('card-fullscreen');
                this.querySelector('i').classList.toggle('fa-expand');
                this.querySelector('i').classList.toggle('fa-compress');
            }
            
            if (this.classList.contains('card-close')) {
                card.remove();
            }
        });
    });
}); 