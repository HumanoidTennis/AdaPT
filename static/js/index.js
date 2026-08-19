window.HELP_IMPROVE_VIDEOJS = false;

function muteVideoElement(video) {
    if (!video) return;
    video.muted = true;
    video.defaultMuted = true;
    if (typeof video.volume === 'number') {
        video.volume = 0;
    }
}

function setupGlobalVideoMute() {
    document.querySelectorAll('video').forEach(muteVideoElement);

    if (!('MutationObserver' in window)) return;

    var observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (!node || node.nodeType !== 1) return;
                if (node.tagName === 'VIDEO') {
                    muteVideoElement(node);
                    return;
                }
                if (typeof node.querySelectorAll === 'function') {
                    node.querySelectorAll('video').forEach(muteVideoElement);
                }
            });
        });
    });

    observer.observe(document.documentElement, {
        childList: true,
        subtree: true
    });
}

// Lightweight analytics helper (uses existing GA4 gtag if present)
function trackEvent(action, label, value) {
    if (typeof gtag === 'function') {
        gtag('event', action, { event_label: label, value: value });
    }
}

// More Works Dropdown Functionality
function toggleMoreWorks() {
    const dropdown = document.getElementById('moreWorksDropdown');
    const button = document.querySelector('.more-works-btn');
    if (!dropdown || !button) return;
    
    if (dropdown.classList.contains('show')) {
        dropdown.classList.remove('show');
        button.classList.remove('active');
        button.setAttribute('aria-expanded', 'false');
    } else {
        dropdown.classList.add('show');
        button.classList.add('active');
        button.setAttribute('aria-expanded', 'true');
    }
}

// Close dropdown when clicking outside
document.addEventListener('click', function(event) {
    const container = document.querySelector('.more-works-container');
    const dropdown = document.getElementById('moreWorksDropdown');
    const button = document.querySelector('.more-works-btn');
    
    if (container && dropdown && button && !container.contains(event.target)) {
        dropdown.classList.remove('show');
        button.classList.remove('active');
        button.setAttribute('aria-expanded', 'false');
    }
});

// Close dropdown on escape key
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        const dropdown = document.getElementById('moreWorksDropdown');
        const button = document.querySelector('.more-works-btn');
        if (dropdown && button) {
            dropdown.classList.remove('show');
            button.classList.remove('active');
            button.setAttribute('aria-expanded', 'false');
        }
    }
});

// Copy BibTeX to clipboard
function copyBibTeX() {
    const bibtexElement = document.getElementById('bibtex-code');
    const button = document.querySelector('.copy-bibtex-btn');
    if (!bibtexElement || !button) return;
    const copyText = button.querySelector('.copy-text');
    if (!copyText) return;
    
    const bibtexText = bibtexElement.textContent.replace(
        /(author=\{)([^}]*)(\})/,
        function(_, prefix, authors, suffix) {
            return prefix + authors.replace(/\s*,\s*/g, ' and ') + suffix;
        }
    );

    navigator.clipboard.writeText(bibtexText).then(function() {
        button.classList.add('copied');
        copyText.textContent = 'Copied';
        
        setTimeout(function() {
            button.classList.remove('copied');
            copyText.textContent = 'Copy';
        }, 2000);
    }).catch(function(err) {
        console.error('Failed to copy: ', err);
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = bibtexText;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        
        button.classList.add('copied');
        copyText.textContent = 'Copied';
        setTimeout(function() {
            button.classList.remove('copied');
            copyText.textContent = 'Copy';
        }, 2000);
    });
}

// Scroll to top functionality
function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
}

function scrollElementNearTop(element, offset) {
    if (!element) return;
    var top = window.scrollY + element.getBoundingClientRect().top - (offset || 16);
    window.scrollTo({
        top: Math.max(0, top),
        behavior: 'smooth'
    });
}

// Show/hide scroll to top button
window.addEventListener('scroll', function() {
    const scrollButton = document.querySelector('.scroll-to-top');
    if (!scrollButton) return;
    if (window.pageYOffset > 300) {
        scrollButton.classList.add('visible');
    } else {
        scrollButton.classList.remove('visible');
    }
});

// Video carousel autoplay when in view
var carouselObserver = null;

function setupVideoCarouselAutoplay() {
    const carouselVideos = document.querySelectorAll('.results-carousel video');

    if (carouselVideos.length === 0) return;
    if (!('IntersectionObserver' in window)) return;

    carouselObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const video = entry.target;
            if (entry.isIntersecting) {
                // Video is in view, play it
                video.play().catch(e => {
                    // Autoplay failed, probably due to browser policy
                    console.log('Autoplay prevented:', e);
                });
            } else {
                // Video is out of view, pause it
                video.pause();
            }
        });
    }, {
        threshold: 0.5 // Trigger when 50% of the video is visible
    });

    carouselVideos.forEach(video => {
        carouselObserver.observe(video);
    });
}

// Lazy-load video: move data-src → src and begin playback
function activateVideo(video) {
    if (video.dataset.lazyActivated) return;
    var source = video.querySelector('source[data-src]');
    if (source) {
        source.src = source.getAttribute('data-src');
        source.removeAttribute('data-src');
        video.load();
    }
    video.muted = true;
    video.dataset.lazyActivated = '1';
    video.addEventListener('loadeddata', function() {
        video.play().catch(function() {});
    }, { once: true });
}

var lazyVideoObserver = null;

function setupLazyVideos() {
    var videos = document.querySelectorAll('.how-section video, .demo-section video');
    if (!videos.length) return;

    if (!('IntersectionObserver' in window)) {
        // Fallback: activate all immediately
        videos.forEach(activateVideo);
        return;
    }

    lazyVideoObserver = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            var video = entry.target;
            if (entry.isIntersecting) {
                activateVideo(video);
                video.play().catch(function() {});
            } else if (video.dataset.lazyActivated) {
                video.pause();
            }
        });
    }, { rootMargin: '200px', threshold: 0.1 });

    videos.forEach(function(video) {
        lazyVideoObserver.observe(video);
    });
}

// Legacy name kept for resumeAllVideos compatibility
function autoplayDemoVideos() {
    if (lazyVideoObserver) {
        document.querySelectorAll('.how-section video, .demo-section video').forEach(function(video) {
            lazyVideoObserver.observe(video);
        });
    } else {
        setupLazyVideos();
    }
}

function setVideoSource(videoElement, sourceUrl) {
    if (!videoElement || !sourceUrl) return;

    // Capture the current frame as a poster so the element keeps its
    // visual content while the new source loads, preventing a flash.
    try {
        if (videoElement.readyState >= 2 && videoElement.videoWidth) {
            var canvas = document.createElement('canvas');
            canvas.width = videoElement.videoWidth;
            canvas.height = videoElement.videoHeight;
            canvas.getContext('2d').drawImage(videoElement, 0, 0);
            videoElement.poster = canvas.toDataURL('image/jpeg', 0.7);
        }
    } catch (e) { /* cross-origin or canvas taint — ignore */ }

    var sourceEl = videoElement.querySelector('source');
    if (!sourceEl) {
        sourceEl = document.createElement('source');
        sourceEl.type = 'video/mp4';
        videoElement.appendChild(sourceEl);
    }
    sourceEl.removeAttribute('data-src');
    sourceEl.src = sourceUrl;
    videoElement.dataset.lazyActivated = '1';
    videoElement.load();

    // Once the new video has a frame, clear the poster so it doesn't
    // show stale content on subsequent pauses.
    videoElement.addEventListener('loadeddata', function clearPoster() {
        videoElement.removeEventListener('loadeddata', clearPoster);
        videoElement.removeAttribute('poster');
    });
}

function activateTab(container, activeButton) {
    if (!container || !activeButton) return;
    container.querySelectorAll('.demo-tab').forEach(function(button) {
        button.classList.remove('active');
        button.setAttribute('aria-selected', 'false');
    });
    activeButton.classList.add('active');
    activeButton.setAttribute('aria-selected', 'true');
}

function setupSingleVideoTabs(containerId, videoId, labelId) {
    var container = document.getElementById(containerId);
    var video = document.getElementById(videoId);
    var labelEl = document.getElementById(labelId);
    if (!container || !video || !labelEl) return;

    var wrap = video.closest('.demo-main-video-wrap');
    var switching = false;

    container.querySelectorAll('.demo-tab').forEach(function(button) {
        button.addEventListener('click', function() {
            var src = button.getAttribute('data-video');
            var label = button.getAttribute('data-label');
            if (!src) return;

            // Guard: skip if already switching or same source
            var currentSrc = (video.querySelector('source') || {}).src || '';
            if (switching || currentSrc === new URL(src, location.href).href) {
                activateTab(container, button);
                return;
            }

            switching = true;
            activateTab(container, button);

            if (wrap) wrap.classList.add('is-switching');

            // Wait for CSS fade-out, then swap source
            setTimeout(function() {
                setVideoSource(video, src);
                if (label) labelEl.textContent = label;

                if (wrap) wrap.classList.add('is-loading');

                function reveal() {
                    if (wrap) {
                        wrap.classList.remove('is-switching');
                        wrap.classList.remove('is-loading');
                    }
                    video.play().catch(function() {});
                    switching = false;
                }

                video.addEventListener('loadeddata', function onLoaded() {
                    video.removeEventListener('loadeddata', onLoaded);
                    reveal();
                });

                // Safety timeout in case loadeddata never fires
                setTimeout(function() {
                    if (switching) reveal();
                }, 3000);
            }, 180);

            trackEvent('demo_tab_switch', containerId + ':' + (label || src));
        });
    });
}

function setupHandResultTabs() {
    var container = document.getElementById('demo-tabs-hands');
    var buttons = container ? Array.from(container.querySelectorAll('.demo-tab[data-hand-panel]')) : [];
    var panels = Array.from(document.querySelectorAll('.hand-results-panel[data-hand-content]'));
    if (!container || !buttons.length || !panels.length) return;

    function setActiveHand(handKey) {
        buttons.forEach(function(button) {
            var isActive = button.getAttribute('data-hand-panel') === handKey;
            button.classList.toggle('active', isActive);
            button.setAttribute('aria-selected', String(isActive));
        });

        panels.forEach(function(panel) {
            panel.classList.toggle('is-active', panel.getAttribute('data-hand-content') === handKey);
        });
    }

    buttons.forEach(function(button) {
        button.addEventListener('click', function() {
            setActiveHand(button.getAttribute('data-hand-panel'));
        });
    });

    setActiveHand('shadow');
}

function setupHandCarousels() {
    var carousels = Array.from(document.querySelectorAll('[data-hand-carousel]'));
    if (!carousels.length) return;

    carousels.forEach(function(carousel) {
        var video = carousel.querySelector('video');
        var label = carousel.querySelector('.demo-video-label');
        var prev = carousel.querySelector('.hand-carousel-arrow--prev');
        var next = carousel.querySelector('.hand-carousel-arrow--next');
        var videos = (carousel.getAttribute('data-videos') || '').split('|').filter(Boolean);
        var labels = (carousel.getAttribute('data-labels') || '').split('|').filter(Boolean);
        var index = 0;
        var switching = false;

        if (!video || !label || !prev || !next || !videos.length) return;

        function render(nextIndex) {
            if (switching) return;
            index = (nextIndex + videos.length) % videos.length;
            switching = true;
            carousel.classList.add('is-switching');

            setTimeout(function() {
                setVideoSource(video, videos[index]);
                label.textContent = labels[index] || '';

                function reveal() {
                    carousel.classList.remove('is-switching');
                    video.play().catch(function() {});
                    switching = false;
                }

                video.addEventListener('loadeddata', function onLoaded() {
                    video.removeEventListener('loadeddata', onLoaded);
                    reveal();
                });

                setTimeout(function() {
                    if (switching) reveal();
                }, 3000);
            }, 180);
        }

        prev.addEventListener('click', function() {
            render(index - 1);
        });

        next.addEventListener('click', function() {
            render(index + 1);
        });
    });
}

function setupDualVideoTabs(containerId, videoAId, videoBId) {
    var container = document.getElementById(containerId);
    var videoA = document.getElementById(videoAId);
    var videoB = document.getElementById(videoBId);
    if (!container || !videoA || !videoB) return;

    var sideBySide = videoA.closest('.demo-side-by-side');
    var switching = false;

    container.querySelectorAll('.demo-tab').forEach(function(button) {
        button.addEventListener('click', function() {
            var sourceA = button.getAttribute('data-mocap');
            var sourceB = button.getAttribute('data-depth');
            if (!sourceA || !sourceB) return;

            if (switching) {
                activateTab(container, button);
                return;
            }

            switching = true;
            activateTab(container, button);

            if (sideBySide) sideBySide.classList.add('is-switching');

            setTimeout(function() {
                setVideoSource(videoA, sourceA);
                setVideoSource(videoB, sourceB);

                var loaded = 0;
                function onOneLoaded() {
                    loaded++;
                    if (loaded >= 2) reveal();
                }

                function reveal() {
                    if (sideBySide) sideBySide.classList.remove('is-switching');
                    videoA.play().catch(function() {});
                    videoB.play().catch(function() {});
                    switching = false;
                }

                videoA.addEventListener('loadeddata', function onA() {
                    videoA.removeEventListener('loadeddata', onA);
                    onOneLoaded();
                });
                videoB.addEventListener('loadeddata', function onB() {
                    videoB.removeEventListener('loadeddata', onB);
                    onOneLoaded();
                });

                // Safety timeout
                setTimeout(function() {
                    if (switching) reveal();
                }, 3000);
            }, 180);

            trackEvent('demo_tab_switch', containerId + ':' + button.textContent.trim());
        });
    });
}

function setupContributionCards() {
    var section = document.querySelector('.contributions-split');
    var summaryCards = Array.from(document.querySelectorAll('.contribution-summary-card'));
    var listItems = Array.from(document.querySelectorAll('.contributions-list-item'));
    var summaryGrid = document.querySelector('.contributions-summary-grid');
    if (!section || !summaryCards.length || !listItems.length || !summaryGrid) return;

    function activateContribution(key, shouldActivate) {
        summaryCards.forEach(function(card) {
            var isActive = shouldActivate && card.getAttribute('data-contribution-key') === key;
            card.classList.toggle('is-active', isActive);
            card.setAttribute('aria-pressed', String(isActive));
        });

        listItems.forEach(function(item) {
            var isActive = shouldActivate && item.getAttribute('data-contribution-key') === key;
            item.classList.toggle('is-active', isActive);
            item.setAttribute('aria-pressed', String(isActive));
        });

        summaryGrid.classList.toggle('has-active', Boolean(shouldActivate));
    }

    listItems.forEach(function(item, index) {
        item.addEventListener('click', function() {
            activateContribution(item.getAttribute('data-contribution-key'), true);
        });

        item.addEventListener('keydown', function(event) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                activateContribution(item.getAttribute('data-contribution-key'), true);
            }
            if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
                event.preventDefault();
                listItems[(index + 1) % listItems.length].focus();
            }
            if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
                event.preventDefault();
                listItems[(index - 1 + listItems.length) % listItems.length].focus();
            }
            if (event.key === 'Escape') {
                event.preventDefault();
                activateContribution('', false);
            }
        });
    });

    activateContribution('', false);
}

function setupMethodOverviewPanels() {
    var hotspots = Array.from(document.querySelectorAll('.how-method-hotspot'));
    var panels = Array.from(document.querySelectorAll('.how-method-panel[data-method-panel-content]'));
    var emptyState = document.querySelector('.how-method-empty[data-method-empty]');
    var plannerCard = document.querySelector('.how-method-panel[data-method-panel-content="planner"] .how-model-card');
    if (!hotspots.length || !panels.length || !emptyState) return;

    function setActivePanel(panelKey) {
        var hasSelection = Boolean(panelKey);

        hotspots.forEach(function(button) {
            var isActive = button.getAttribute('data-method-panel') === panelKey;
            button.classList.toggle('is-active', isActive);
            button.setAttribute('aria-pressed', String(isActive));
        });

        panels.forEach(function(panel) {
            panel.classList.toggle('is-active', panel.getAttribute('data-method-panel-content') === panelKey);
        });

        emptyState.classList.toggle('is-active', !hasSelection);
    }

    hotspots.forEach(function(button) {
        button.addEventListener('click', function() {
            var panelKey = button.getAttribute('data-method-panel');
            setActivePanel(panelKey);
            if (panelKey === 'planner') {
                requestAnimationFrame(function() {
                    scrollElementNearTop(plannerCard, 18);
                });
            }
        });
    });

    setActivePanel('');
}

function setupPlannerSkillTabs() {
    var tabs = Array.from(document.querySelectorAll('.how-planner-hotspot[data-skill-panel]'));
    var panels = Array.from(document.querySelectorAll('.how-planner-skill-panel[data-skill-content]'));
    var emptyState = document.querySelector('[data-planner-empty]');
    var hotspotWrap = document.querySelector('.how-planner-hotspots');
    var plannerCard = document.querySelector('.how-method-panel[data-method-panel-content="planner"] .how-model-card');
    var placeholderPanel = document.querySelector('.how-planner-skill-panel[data-skill-content="placeholder"]');
    var placeholderTitle = document.getElementById('how-planner-placeholder-title');
    var placeholderText = document.getElementById('how-planner-placeholder-text');
    if (!tabs.length || !panels.length || !emptyState) return;

    function setActiveSkill(skillKey) {
        var hasSelection = Boolean(skillKey);
        var matchedPanel = null;

        tabs.forEach(function(tab) {
            var isActive = tab.getAttribute('data-skill-panel') === skillKey;
            tab.classList.toggle('is-active', isActive);
            tab.setAttribute('aria-pressed', String(isActive));
        });

        if (hotspotWrap) {
            hotspotWrap.classList.toggle('has-active', hasSelection);
        }

        panels.forEach(function(panel) {
            var isDirectMatch = panel.getAttribute('data-skill-content') === skillKey;
            if (isDirectMatch) matchedPanel = panel;
            var isActive = isDirectMatch;
            panel.classList.toggle('is-active', isActive);
            if (isActive) {
                panel.querySelectorAll('video').forEach(function(video) {
                    activateVideo(video);
                    video.play().catch(function() {});
                });
            } else {
                panel.querySelectorAll('video').forEach(function(video) {
                    video.pause();
                });
            }
        });

        if (hasSelection && !matchedPanel && placeholderPanel) {
            var activeTab = tabs.find(function(tab) {
                return tab.getAttribute('data-skill-panel') === skillKey;
            });
            var skillName = activeTab ? (activeTab.getAttribute('data-skill-name') || skillKey) : skillKey;
            placeholderPanel.classList.add('is-active');
            if (placeholderTitle) placeholderTitle.textContent = skillName + ' references coming soon';
            if (placeholderText) placeholderText.textContent = 'Reference videos for ' + skillName + ' will be added soon.';
        } else if (placeholderPanel) {
            placeholderPanel.classList.remove('is-active');
        }

        emptyState.classList.toggle('is-active', !hasSelection);
    }

    tabs.forEach(function(tab) {
        tab.addEventListener('click', function() {
            setActiveSkill(tab.getAttribute('data-skill-panel'));
            requestAnimationFrame(function() {
                scrollElementNearTop(plannerCard, 18);
            });
        });
    });

    setActiveSkill('');
}

function pauseAllVideos() {
    document.querySelectorAll('video').forEach(function(v) {
        if (v.closest('.hero-video-grid')) return;
        v.pause();
    });
    if (carouselObserver) carouselObserver.disconnect();
    if (lazyVideoObserver) lazyVideoObserver.disconnect();
}

function resumeAllVideos() {
    // Re-observe carousel videos
    if (carouselObserver) {
        document.querySelectorAll('.results-carousel video').forEach(function(video) {
            carouselObserver.observe(video);
        });
    }
    // Re-observe lazy videos
    if (lazyVideoObserver) {
        document.querySelectorAll('.how-section video, .demo-section video').forEach(function(video) {
            lazyVideoObserver.observe(video);
        });
    }
}

function setupMujocoSessionLauncher() {
    var section = document.querySelector('.mujoco-session-section');
    var frameWrap = document.querySelector('.mujoco-session-frame-wrap');
    var startButton = document.getElementById('start-mujoco-btn');
    var iframe = document.getElementById('mujoco-session-frame');
    var closeButton = document.getElementById('close-mujoco-btn');
    var phoneDisabledNote = document.getElementById('mujoco-session-disabled-note');
    if (!section || !frameWrap || !startButton || !iframe) return;

    // MuJoCo now works on mobile — no phone gate

    var loadingOverlay = document.getElementById('mujoco-loading-overlay');

    startButton.addEventListener('click', function() {
        var iframeSrc = iframe.getAttribute('data-src');
        if (!iframeSrc) return;

        // Show loading overlay
        if (loadingOverlay) loadingOverlay.hidden = false;

        iframe.src = iframeSrc;
        frameWrap.classList.add('is-started');
        startButton.disabled = true;
        startButton.setAttribute('aria-disabled', 'true');
        startButton.textContent = 'Session Running';
        if (closeButton) closeButton.hidden = false;

        // Hide overlay once iframe signals ready or after timeout
        function hideOverlay() { if (loadingOverlay) loadingOverlay.hidden = true; }
        window.addEventListener('message', function onReady(e) {
            if (e.data && e.data.type === 'hot-ready') {
                window.removeEventListener('message', onReady);
                hideOverlay();
            }
        });
        setTimeout(hideOverlay, 30000); // fallback: hide after 30s max

        trackEvent('mujoco_session', 'start');
    });

    if (closeButton) {
        closeButton.addEventListener('click', function() {
            // Signal iframe to clean up resources before tearing down
            try { iframe.contentWindow.postMessage({ type: 'hot-close' }, '*'); } catch(e) {}
            // Brief delay for cleanup, then tear down
            setTimeout(function() {
                iframe.src = 'about:blank';
                frameWrap.classList.remove('is-started');
                if (loadingOverlay) loadingOverlay.hidden = true;
                startButton.disabled = false;
                startButton.removeAttribute('aria-disabled');
                startButton.textContent = 'Start Live MuJoCo Session';
                closeButton.hidden = true;
            }, 150);
            trackEvent('mujoco_session', 'close');
        });
    }
}

/* ── Scroll-triggered reveal animations ── */
function setupRevealAnimations() {
    var els = document.querySelectorAll('.reveal, .reveal--left, .reveal--right, .reveal--scale, .reveal--fade');
    if (!els.length || !('IntersectionObserver' in window)) {
        // Fallback: show everything immediately
        els.forEach(function(el) { el.classList.add('is-visible'); });
        return;
    }

    // Assign stagger indices to children of .reveal-stagger parents
    document.querySelectorAll('.reveal-stagger').forEach(function(parent) {
        var children = parent.querySelectorAll('.reveal, .reveal--left, .reveal--right, .reveal--scale');
        children.forEach(function(child, i) {
            child.style.setProperty('--reveal-i', i);
        });
    });

    var observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });

    els.forEach(function(el) { observer.observe(el); });
}

/* ── Bar chart grow animation ── */
function setupBarChartAnimation() {
    var card = document.querySelector('.stats-card');
    if (!card || !('IntersectionObserver' in window)) return;

    var rects = card.querySelectorAll('rect');
    if (!rects.length) return;

    // Store original values and collapse to baseline
    var originals = [];
    rects.forEach(function(rect) {
        var y = parseFloat(rect.getAttribute('y'));
        var h = parseFloat(rect.getAttribute('height'));
        originals.push({ y: y, h: h });
        rect.setAttribute('y', y + h);
        rect.setAttribute('height', 0);
        rect.style.transition = 'none';
    });

    var observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                rects.forEach(function(rect, i) {
                    setTimeout(function() {
                        rect.style.transition = 'y 0.5s cubic-bezier(0.4,0,0.2,1), height 0.5s cubic-bezier(0.4,0,0.2,1)';
                        rect.setAttribute('y', originals[i].y);
                        rect.setAttribute('height', originals[i].h);
                    }, i * 30);
                });
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.2 });

    observer.observe(card);
}

/* ── Line chart stats card animation ── */
function setupLineChartAnimation() {
    var cards = document.querySelectorAll('.stats-card');
    if (cards.length < 2 || !('IntersectionObserver' in window)) return;

    var lineCard = cards[1]; // second stats card
    var observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.25 });

    observer.observe(lineCard);
}

function setupOutlinePanel() {
    var panel = document.querySelector('.outline-panel');
    var outlineLinks = Array.from(document.querySelectorAll('.outline-panel .outline-link[data-outline-link]'));
    if (!outlineLinks.length) return;

    // --- Fold / unfold toggle ---
    var titleEl = document.getElementById('outline-toggle');
    if (titleEl && panel) {
        titleEl.addEventListener('click', function(e) {
            e.preventDefault();
            panel.classList.toggle('is-collapsed');
        });
    }

    var sectionEntries = outlineLinks
        .map(function(link) {
            var id = link.getAttribute('data-outline-link');
            var section = id ? document.getElementById(id) : null;
            return section ? { id: id, section: section } : null;
        })
        .filter(Boolean);
    if (!sectionEntries.length) return;

    function setActiveLink(id) {
        outlineLinks.forEach(function(link) {
            var isActive = link.getAttribute('data-outline-link') === id;
            link.classList.toggle('active', isActive);
            link.setAttribute('aria-current', isActive ? 'true' : 'false');
        });
    }

    function updateActiveFromScroll() {
        // Track the section that has crossed a stable anchor point.
        var anchorY = window.innerHeight * 0.32;
        var activeId = sectionEntries[0].id;

        for (var i = 0; i < sectionEntries.length; i += 1) {
            var item = sectionEntries[i];
            var top = item.section.getBoundingClientRect().top;
            if (top <= anchorY) {
                activeId = item.id;
            } else {
                break;
            }
        }

        setActiveLink(activeId);
    }

    window.addEventListener('scroll', updateActiveFromScroll, { passive: true });
    window.addEventListener('resize', updateActiveFromScroll);

    updateActiveFromScroll();
}

function setupAffiliationsToggle() {
    var wrap = document.querySelector('.affiliations-wrap');
    var button = document.querySelector('.affiliations-toggle');
    if (!wrap || !button) return;

    button.addEventListener('click', function() {
        var isOpen = wrap.classList.toggle('is-open');
        button.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });
}

/* ── 3D Card Tilt on Contribution Cards ── */
function setupCardTilt() {
    if (!window.matchMedia('(hover: hover)').matches) return;

    var cards = document.querySelectorAll('.contribution-card');
    cards.forEach(function(card) {
        // Add highlight overlay div
        var highlight = document.createElement('div');
        highlight.className = 'card-tilt-highlight';
        highlight.setAttribute('aria-hidden', 'true');
        card.appendChild(highlight);

        card.addEventListener('mousemove', function(e) {
            var rect = card.getBoundingClientRect();
            var x = e.clientX - rect.left;
            var y = e.clientY - rect.top;
            var centerX = rect.width / 2;
            var centerY = rect.height / 2;
            var rotateY = ((x - centerX) / centerX) * 4;
            var rotateX = ((centerY - y) / centerY) * 4;

            card.style.transform = 'perspective(800px) rotateX(' + rotateX + 'deg) rotateY(' + rotateY + 'deg) translateY(-2px)';
            card.style.setProperty('--tilt-x', x + 'px');
            card.style.setProperty('--tilt-y', y + 'px');
        });

        card.addEventListener('mouseleave', function() {
            card.style.transform = '';
        });
    });
}

/* ── Mouse-following Gradient Spotlight on Hero ── */
function setupHeroSpotlight() {
    if (!window.matchMedia('(hover: hover)').matches) return;

    var hero = document.querySelector('.hero-main');
    if (!hero) return;

    var rafId = null;
    var mouseX = 0;
    var mouseY = 0;

    hero.addEventListener('mousemove', function(e) {
        mouseX = e.clientX;
        mouseY = e.clientY;

        if (!rafId) {
            rafId = requestAnimationFrame(function() {
                var rect = hero.getBoundingClientRect();
                var x = mouseX - rect.left;
                var y = mouseY - rect.top;
                hero.style.setProperty('--mouse-x', x + 'px');
                hero.style.setProperty('--mouse-y', y + 'px');
                rafId = null;
            });
        }
    });
}

/* ── Distance Field Contour Visualization (Contributions) ── */
function setupDFContours() {
    if (!window.matchMedia('(hover: hover)').matches) return;

    var section = document.querySelector('.contributions-section');
    if (!section) return;

    var canvas = document.createElement('canvas');
    canvas.className = 'df-contour-canvas';
    canvas.setAttribute('aria-hidden', 'true');
    section.appendChild(canvas);

    var ctx = canvas.getContext('2d');
    var cards = section.querySelectorAll('.contribution-card');
    if (!cards.length) return;

    var raf = null;
    var mx = -9999, my = -9999;
    var STEP = 10;
    var INTERVAL = 36;
    var BAND = 2;
    var RADIUS = 200;

    // Returns { dist, nx, ny } — distance and nearest point on card surface
    function sdf(px, py) {
        var best = 1e9, nx = px, ny = py;
        var sr = section.getBoundingClientRect();
        for (var i = 0; i < cards.length; i++) {
            var r = cards[i].getBoundingClientRect();
            var l = r.left - sr.left, t = r.top - sr.top;
            var ri = l + r.width, b = t + r.height;
            // Clamp to card rect to find nearest surface point
            var cx = Math.max(l, Math.min(px, ri));
            var cy = Math.max(t, Math.min(py, b));
            var ddx = px - cx, ddy = py - cy;
            var d = Math.sqrt(ddx * ddx + ddy * ddy);
            if (d < best) { best = d; nx = cx; ny = cy; }
        }
        return { dist: best, nx: nx, ny: ny };
    }

    function render() {
        var w = section.offsetWidth;
        var h = section.offsetHeight;
        if (canvas.width !== w) canvas.width = w;
        if (canvas.height !== h) canvas.height = h;
        ctx.clearRect(0, 0, w, h);
        if (mx < -5000) return;

        var x0 = Math.max(0, (mx - RADIUS) / STEP | 0) * STEP;
        var x1 = Math.min(w, mx + RADIUS);
        var y0 = Math.max(0, (my - RADIUS) / STEP | 0) * STEP;
        var y1 = Math.min(h, my + RADIUS);

        for (var x = x0; x <= x1; x += STEP) {
            for (var y = y0; y <= y1; y += STEP) {
                var sd = sdf(x, y);
                if (sd.dist < 4) continue;
                var mod = sd.dist % INTERVAL;
                var near = Math.min(mod, INTERVAL - mod);
                if (near >= BAND) continue;

                var contour = 1 - near / BAND;
                var ddx = x - mx, ddy = y - my;
                var dist = Math.sqrt(ddx * ddx + ddy * ddy);
                var fade = 1 - dist / RADIUS;
                if (fade <= 0) continue;
                fade *= fade;

                var a = 0.14 * contour * fade;
                ctx.fillStyle = 'rgba(37,99,235,' + a.toFixed(3) + ')';
                ctx.fillRect(x - 1, y - 1, 3, 3);
            }
        }

        // Probe: arrow pointing toward nearest surface
        var probe = sdf(mx, my);
        if (probe.dist > 8) {
            var dirX = probe.nx - mx, dirY = probe.ny - my;
            var len = Math.sqrt(dirX * dirX + dirY * dirY);
            var ux = dirX / len, uy = dirY / len;

            // Arrow shaft
            var shaftLen = Math.min(28, probe.dist - 6);
            var sx = mx + ux * 8, sy = my + uy * 8;
            var ex = mx + ux * (8 + shaftLen), ey = my + uy * (8 + shaftLen);
            ctx.strokeStyle = 'rgba(37,99,235,0.35)';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(sx, sy);
            ctx.lineTo(ex, ey);
            ctx.stroke();

            // Arrowhead
            var headLen = 6;
            var ax = -ux * headLen + uy * headLen * 0.5;
            var ay = -uy * headLen - ux * headLen * 0.5;
            var bx = -ux * headLen - uy * headLen * 0.5;
            var by = -uy * headLen + ux * headLen * 0.5;
            ctx.fillStyle = 'rgba(37,99,235,0.35)';
            ctx.beginPath();
            ctx.moveTo(ex, ey);
            ctx.lineTo(ex + ax, ey + ay);
            ctx.lineTo(ex + bx, ey + by);
            ctx.closePath();
            ctx.fill();
        }

        // Crosshair + distance label
        ctx.strokeStyle = 'rgba(37,99,235,0.2)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(mx, my, 5, 0, Math.PI * 2);
        ctx.stroke();
        ctx.font = '600 10px Inter, system-ui, sans-serif';
        ctx.fillStyle = 'rgba(37,99,235,0.4)';
        ctx.fillText('d\u2009=\u2009' + probe.dist.toFixed(0), mx + 12, my - 8);
    }

    section.addEventListener('mousemove', function(e) {
        var sr = section.getBoundingClientRect();
        mx = e.clientX - sr.left;
        my = e.clientY - sr.top;
        if (!raf) {
            raf = requestAnimationFrame(function() { render(); raf = null; });
        }
    });

    section.addEventListener('mouseleave', function() {
        mx = -9999; my = -9999;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    });
}

/* ── Cursor Trail — Root Trajectory Visualization ── */
function setupCursorTrail() {
    if (!window.matchMedia('(hover: hover)').matches) return;

    var zones = document.querySelectorAll('.demo-section, .how-section');
    if (!zones.length) return;

    var canvas = document.createElement('canvas');
    canvas.className = 'cursor-trail-canvas';
    canvas.setAttribute('aria-hidden', 'true');
    document.body.appendChild(canvas);

    var ctx = canvas.getContext('2d');
    var pts = [];
    var LIFE = 400;
    var raf = null;

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    function inZone(cy) {
        for (var i = 0; i < zones.length; i++) {
            var r = zones[i].getBoundingClientRect();
            if (cy >= r.top && cy <= r.bottom) return true;
        }
        return false;
    }

    document.addEventListener('mousemove', function(e) {
        if (!inZone(e.clientY)) return;
        pts.push({ x: e.clientX, y: e.clientY, t: performance.now() });
        if (!raf) tick();
    });

    function tick() {
        raf = requestAnimationFrame(function() {
            var now = performance.now();
            while (pts.length && now - pts[0].t > LIFE) pts.shift();

            ctx.clearRect(0, 0, canvas.width, canvas.height);
            for (var i = 0; i < pts.length; i++) {
                var age = (now - pts[i].t) / LIFE;
                var a = 0.15 * (1 - age);
                var r = 2 * (1 - age * 0.5);
                ctx.beginPath();
                ctx.arc(pts[i].x, pts[i].y, r, 0, Math.PI * 2);
                ctx.fillStyle = 'rgba(37,99,235,' + a.toFixed(3) + ')';
                ctx.fill();
            }

            raf = null;
            if (pts.length) tick();
        });
    }
}

/* ── Hero DF Rings — Gentle Mouse Tracking ── */
function setupHeroDFTracking() {
    if (!window.matchMedia('(hover: hover)').matches) return;

    var hero = document.querySelector('.hero-main');
    var rings = document.querySelector('.hero-df-rings');
    if (!hero || !rings) return;

    var curX = 0, curY = 0, tgtX = 0, tgtY = 0;
    var raf = null;

    hero.addEventListener('mousemove', function(e) {
        var rect = hero.getBoundingClientRect();
        tgtX = ((e.clientX - rect.left) / rect.width - 0.5) * 4;
        tgtY = ((e.clientY - rect.top) / rect.height - 0.5) * 4;
        if (!raf) animate();
    });

    hero.addEventListener('mouseleave', function() {
        tgtX = 0; tgtY = 0;
        if (!raf) animate();
    });

    function animate() {
        raf = requestAnimationFrame(function() {
            curX += (tgtX - curX) * 0.08;
            curY += (tgtY - curY) * 0.08;
            rings.style.transform = 'translate(calc(-50% + ' + curX.toFixed(2) + '%), calc(-50% + ' + curY.toFixed(2) + '%))';
            raf = null;
            if (Math.abs(tgtX - curX) > 0.01 || Math.abs(tgtY - curY) > 0.01) animate();
        });
    }
}

/* ── Video glow: add is-visible to demo-main-video-wrap when in view ── */
function setupVideoGlow() {
    var wraps = document.querySelectorAll('.demo-main-video-wrap');
    if (!wraps.length || !('IntersectionObserver' in window)) return;

    var observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            entry.target.classList.toggle('is-visible', entry.isIntersecting);
        });
    }, { threshold: 0.3 });

    wraps.forEach(function(wrap) { observer.observe(wrap); });
}

document.addEventListener('DOMContentLoaded', function() {
    setupGlobalVideoMute();

    var options = {
        slidesToScroll: 1,
        slidesToShow: 1,
        loop: true,
        infinite: true,
        autoplay: true,
        autoplaySpeed: 5000
    };

    if (window.bulmaCarousel && typeof window.bulmaCarousel.attach === 'function') {
        window.bulmaCarousel.attach('.carousel', options);
    }
    if (window.bulmaSlider && typeof window.bulmaSlider.attach === 'function') {
        window.bulmaSlider.attach();
    }

    // Core interactions first (must work even if optional features fail).
    setupSingleVideoTabs('demo-tabs-generalization', 'demo-video-generalization', 'demo-label-generalization');
    setupSingleVideoTabs('demo-tabs-longhorizon', 'demo-video-longhorizon', 'demo-label-longhorizon');
    setupSingleVideoTabs('demo-tabs-recovery', 'demo-video-recovery', 'demo-label-recovery');
    setupHandResultTabs();
    setupHandCarousels();
    setupDualVideoTabs('demo-tabs-perception', 'demo-video-mocap', 'demo-video-depth');
    setupContributionCards();
    setupMethodOverviewPanels();
    setupPlannerSkillTabs();
    setupMujocoSessionLauncher();
    setupAffiliationsToggle();
    setupOutlinePanel();
    setupLazyVideos();

    // Scroll-triggered reveal animations
    setupRevealAnimations();
    setupBarChartAnimation();
    setupLineChartAnimation();

    // Fancy visual enhancements
    setupCardTilt();
    setupHeroSpotlight();
    setupVideoGlow();
    setupDFContours();
    setupCursorTrail();
    setupHeroDFTracking();

    // Non-critical enhancements are isolated so they cannot block button behavior.
    try {
        setupVideoCarouselAutoplay();
    } catch (error) {
        console.warn('Video carousel autoplay enhancement disabled:', error);
    }
});
