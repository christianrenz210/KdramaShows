$(function () {

    // ========== THEME TOGGLE ==========
    var theme = localStorage.getItem('theme') || 'dark';
    $('html').attr('data-bs-theme', theme);
    updateThemeIcon(theme);

    $('#themeToggle').on('click', function () {
        var current = $('html').attr('data-bs-theme');
        var next = current === 'dark' ? 'light' : 'dark';
        $('html').attr('data-bs-theme', next);
        localStorage.setItem('theme', next);
        updateThemeIcon(next);
    });

    function updateThemeIcon(t) {
        var icon = t === 'dark' ? 'bi-sun-fill' : 'bi-moon-fill';
        $('#themeToggle i').attr('class', 'bi ' + icon);
    }

    // ========== DETAIL PAGE: TVmaze Enrichment ==========
    if ($('#detailHeader').length) {
        var pathParts = window.location.pathname.split('/');
        var mediaType = pathParts[2];
        var imdbId = pathParts[3];

        if (mediaType === 'tv' && imdbId) {
            $.getJSON('/api/tvmaze/' + imdbId, function (data) {
                if (data.error) return;
                if (data.poster) {
                    var posterHtml = '<img src="' + data.poster + '" class="img-fluid rounded shadow" alt="' + escapeHtml(data.title) + '">';
                    $('#posterContainer').html(posterHtml);
                }
                if (data.title) $('#detailTitle').text(data.title);
                var metaHtml = '';
                if (data.year) metaHtml += '<span class="badge bg-secondary">' + data.year + '</span> ';
                if (data.rating) metaHtml += '<span class="badge bg-warning text-dark"><i class="bi bi-star-fill me-1"></i>' + data.rating + '</span> ';
                if (data.status) metaHtml += '<span class="badge bg-info text-dark">' + data.status + '</span> ';
                if (data.language) metaHtml += '<span class="badge bg-light text-dark">' + data.language + '</span> ';
                $('#detailMeta').html(metaHtml);
                if (data.genres && data.genres.length) {
                    var ghtml = '';
                    $.each(data.genres, function (i, g) { ghtml += '<span class="badge bg-kdrama me-1">' + g + '</span>'; });
                    $('#detailGenres').html(ghtml);
                }
                if (data.summary) $('#detailSummary').text(data.summary);
            });
        }
    }

    // ========== DETAIL PAGE: KissKh HLS Player ==========
    var kisskhVideo = document.getElementById('kisskhVideo');
    if (kisskhVideo && typeof kisskhEpisodes !== 'undefined') {
        var hls = null;
        var kisskhDramaTitle = kisskhVideo.getAttribute('data-title') || '';
        var kisskhDramaId = kisskhVideo.getAttribute('data-kisskh-id') || '0';

        function setLoaderText(text) {
            var sub = $('#playerLoaderSub');
            if (sub.length) sub.text(text);
        }

        function showOverlay(show) {
            var ov = $('#playerOverlay');
            if (ov.length) {
                if (show) ov.removeClass('hidden'); else ov.addClass('hidden');
            }
        }

        function startVideoPlayback(streamUrl, streamType) {
            var status = $('#playerStatus');
            if (!streamUrl) {
                status.html('<span class="text-danger"><i class="bi bi-exclamation-circle me-1"></i>No stream URL</span>');
                showOverlay(false);
                return;
            }
            status.html('<span class="text-success"><i class="bi bi-check-circle me-1"></i>Stream ready</span>');
            setLoaderText('Starting playback...');

            if (hls) {
                hls.destroy();
                hls = null;
            }

            function onPlayStart() {
                showOverlay(false);
                kisskhVideo.removeEventListener('playing', onPlayStart);
                kisskhVideo.removeEventListener('canplay', onPlayStart);
                clearTimeout(window._ovFallback);
            }
            kisskhVideo.addEventListener('playing', onPlayStart);
            kisskhVideo.addEventListener('canplay', onPlayStart);

            // Fallback: hide overlay after 30s if play never starts
            window._ovFallback = setTimeout(function () {
                showOverlay(false);
            }, 30000);

            if (streamUrl.indexOf('.mp4') !== -1 || streamType === 'direct') {
                kisskhVideo.src = streamUrl;
                kisskhVideo.play().catch(function () {});
            } else if (Hls.isSupported()) {
                hls = new Hls({
                    enableWorker: false,
                    maxBufferLength: 30,
                    maxMaxBufferLength: 60,
                    manifestLoadingTimeOut: 30000,
                    levelLoadingTimeOut: 30000,
                    fragLoadingTimeOut: 60000,
                });
                hls.loadSource(streamUrl);
                hls.attachMedia(kisskhVideo);
                var hlsRecoverCount = 0;
                hls.on(Hls.Events.MANIFEST_PARSED, function () {
                    hlsRecoverCount = 0;
                    setLoaderText('Buffering...');
                    kisskhVideo.play().catch(function () {});
                });
                hls.on(Hls.Events.ERROR, function (event, data) {
                    if (data.fatal) {
                        if (data.type === Hls.ErrorTypes.NETWORK_ERROR && hlsRecoverCount < 3) {
                            hlsRecoverCount++;
                            status.html('<span class="text-warning"><i class="bi bi-arrow-repeat me-1"></i>Retrying... (' + hlsRecoverCount + '/3)</span>');
                            setLoaderText('Retrying (' + hlsRecoverCount + '/3)...');
                            setTimeout(function () {
                                hls.startLoad();
                            }, 2000 * hlsRecoverCount);
                            return;
                        }
                        status.html('<span class="text-danger"><i class="bi bi-exclamation-circle me-1"></i>Stream error: ' + data.type + (data.response ? ' (' + data.response.code + ')' : '') + '</span>');
                        showOverlay(false);
                    }
                });
            } else if (kisskhVideo.canPlayType('application/vnd.apple.mpegurl')) {
                kisskhVideo.src = streamUrl;
                kisskhVideo.play().catch(function () {});
            } else {
                status.html('<span class="text-danger"><i class="bi bi-exclamation-circle me-1"></i>HLS not supported in this browser</span>');
                showOverlay(false);
            }
        }

        function loadKisskhStream(episodeId, epNum) {
            var status = $('#playerStatus');
            status.html('<span class="spinner-border spinner-border-sm me-1" role="status"></span> Loading stream...');

            var subtitleStatus = $('#subtitleStatus');
            subtitleStatus.html('');

            var epLabel = $('#currentEpisodeLabel');
            if (epLabel.length) epLabel.text(epNum);

            showOverlay(true);
            setLoaderText('Requesting stream...');

            var params = {drama_id: kisskhDramaId, ep_num: epNum, title: kisskhDramaTitle};
            $.ajax({
                url: '/api/kisskh/stream/' + episodeId,
                data: params,
                dataType: 'json',
                timeout: 60000,
                success: function (data) {
                    if (data.error) {
                        var errMsg = data.error;
                        if (data.error === 'not_released') {
                            errMsg = 'Episode ' + (data.ep_num || '') + ' not yet released. Latest: Episode ' + (data.max_ep || '');
                        }
                        status.html('<span class="text-warning"><i class="bi bi-clock me-1"></i>' + errMsg + '</span>');
                        showOverlay(false);
                        return;
                    }
                    setLoaderText('Stream found, loading...');
                    var streamUrl = data.url || data.direct;
                    var streamType = data.type || '';
                    startVideoPlayback(streamUrl, streamType);
                    loadSubtitles(episodeId);
                }
            }).fail(function (jqxhr) {
                var msg = 'Episode not available.';
                try {
                    var errResp = JSON.parse(jqxhr.responseText);
                    if (errResp.error === 'not_released') {
                        var ep = errResp.ep_num || '';
                        var max = errResp.max_ep || '';
                        msg = 'Episode ' + ep + ' not yet released. Latest available: Episode ' + max;
                        status.html('<span class="text-warning"><i class="bi bi-clock me-1"></i>' + msg + '</span>');
                        showOverlay(false);
                        return;
                    }
                    if (errResp.error) msg = errResp.error;
                } catch(e) {}
                status.html('<span class="text-danger"><i class="bi bi-exclamation-circle me-1"></i>' + msg + '</span>');
                showOverlay(false);
            });
        }

        function loadSubtitles(episodeId) {
            var subtitleStatus = $('#subtitleStatus');
            $.ajax({
                url: '/api/kisskh/sub/' + episodeId,
                dataType: 'text',
                timeout: 30000,
                success: function (vttData) {
                    var oldTrack = kisskhVideo.querySelector('track');
                    if (oldTrack) {
                        URL.revokeObjectURL(oldTrack.src);
                        oldTrack.remove();
                    }

                    var blob = new Blob([vttData], {type: 'text/vtt'});
                    var blobUrl = URL.createObjectURL(blob);
                    var track = document.createElement('track');
                    track.kind = 'subtitles';
                    track.label = 'English';
                    track.srclang = 'en';
                    track.src = blobUrl;
                    track.default = true;
                    kisskhVideo.appendChild(track);

                    // Poll until track appears in textTracks, then enable
                    var pollInterval = setInterval(function () {
                        for (var i = 0; i < kisskhVideo.textTracks.length; i++) {
                            var tt = kisskhVideo.textTracks[i];
                            if (tt.kind === 'subtitles') {
                                tt.mode = 'showing';
                                clearInterval(pollInterval);
                                break;
                            }
                        }
                    }, 100);

                    // Stop polling after 5s
                    setTimeout(function () { clearInterval(pollInterval); }, 5000);

                    subtitleStatus.html('<span class="text-success"><i class="bi bi-cc-circle me-1"></i>CC available</span>');
                    addCcSelector(true);
                },
                error: function () {
                    subtitleStatus.html('<span class="text-muted"><i class="bi bi-cc-circle me-1"></i>No subtitles</span>');
                    addCcSelector(false);
                }
            });
        }

        function addCcSelector(hasSubs) {
            var existing = document.querySelector('.cc-selector');
            if (existing) existing.remove();
            var wrapper = document.createElement('div');
            wrapper.className = 'cc-selector';
            if (!hasSubs) wrapper.style.display = 'none';

            var btn = document.createElement('button');
            btn.className = 'cc-toggle-btn cc-active';
            btn.innerHTML = '<i class="bi bi-cc-circle"></i>';
            btn.title = 'Subtitles';
            btn.setAttribute('aria-label', 'Subtitles');
            wrapper.appendChild(btn);

            var menu = document.createElement('div');
            menu.className = 'cc-menu';
            menu.style.display = 'none';

            var trackList = document.createElement('div');
            trackList.className = 'cc-track-list';
            menu.appendChild(trackList);

            function populateTracks() {
                trackList.innerHTML = '';
                var offItem = document.createElement('div');
                offItem.className = 'cc-menu-item';
                offItem.textContent = 'Off';
                offItem.addEventListener('click', function (e) {
                    e.stopPropagation();
                    for (var i = 0; i < kisskhVideo.textTracks.length; i++) {
                        if (kisskhVideo.textTracks[i].kind === 'subtitles')
                            kisskhVideo.textTracks[i].mode = 'hidden';
                    }
                    btn.classList.remove('cc-active');
                    menu.style.display = 'none';
                    populateTracks();
                });
                trackList.appendChild(offItem);

                var activeCount = 0;
                for (var i = 0; i < kisskhVideo.textTracks.length; i++) {
                    var tt = kisskhVideo.textTracks[i];
                    if (tt.kind !== 'subtitles') continue;
                    var item = document.createElement('div');
                    var isActive = tt.mode === 'showing';
                    item.className = 'cc-menu-item' + (isActive ? ' cc-menu-active' : '');
                    item.textContent = tt.label || 'Track ' + (i + 1);
                    if (isActive) activeCount++;
                    item.addEventListener('click', function (track) {
                        return function (e) {
                            e.stopPropagation();
                            for (var j = 0; j < kisskhVideo.textTracks.length; j++) {
                                var t = kisskhVideo.textTracks[j];
                                if (t.kind === 'subtitles')
                                    t.mode = t === track ? 'showing' : 'hidden';
                            }
                            btn.classList.add('cc-active');
                            menu.style.display = 'none';
                            populateTracks();
                        };
                    }(tt));
                    trackList.appendChild(item);
                }
                if (activeCount === 0 && !offItem.classList.contains('cc-menu-active')) {
                    offItem.classList.add('cc-menu-active');
                }
            }

            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                e.preventDefault();
                populateTracks();
                menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
            });

            document.addEventListener('click', function (e) {
                if (!wrapper.contains(e.target)) menu.style.display = 'none';
            });

            wrapper.appendChild(menu);
            if (kisskhVideo.parentNode) {
                kisskhVideo.parentNode.style.position = 'relative';
                kisskhVideo.parentNode.appendChild(wrapper);
            }

            kisskhVideo.textTracks.addEventListener('addtrack', populateTracks);
            kisskhVideo.textTracks.addEventListener('removetrack', populateTracks);
        }

        // Load first episode
        var firstEp = kisskhEpisodes[0];
        loadKisskhStream(firstEp.id, firstEp.number);

        // Episode switcher
        $('#loadKisskhEpisodeBtn').on('click', function () {
            var opt = $('#kisskhEpisodeSelect option:selected');
            var epId = opt.val();
            var epNum = opt.data('number');
            loadKisskhStream(epId, epNum);
        });

        // ========== CUSTOM CONTROLS ==========
        var controlsEl = document.getElementById('customControls');
        var playBtn = document.getElementById('playBtn');
        var seekBar = document.getElementById('seekBar');
        var volumeBar = document.getElementById('volumeBar');
        var volumeBtn = document.getElementById('volumeBtn');
        var timeDisplay = document.getElementById('timeDisplay');
        var fullscreenBtn = document.getElementById('fullscreenBtn');
        var rewindBtn = document.getElementById('rewindBtn');
        var forwardBtn = document.getElementById('forwardBtn');
        var bufferBar = document.getElementById('bufferBar');
        var qualityDisplay = document.getElementById('qualityDisplay');
        var playerContainer = document.getElementById('playerContainer');

        if (controlsEl && playBtn) {
            var controlsTimeout;
            var isSeeking = false;

            function formatTime(t) {
                if (isNaN(t) || !isFinite(t)) return '0:00';
                var m = Math.floor(t / 60);
                var s = Math.floor(t % 60);
                return m + ':' + (s < 10 ? '0' : '') + s;
            }

            function updatePlayBtn() {
                var icon = kisskhVideo.paused ? 'bi-play-fill' : 'bi-pause-fill';
                playBtn.innerHTML = '<i class="bi ' + icon + '"></i>';
            }

            function updateTime() {
                if (!isSeeking) {
                    seekBar.value = (kisskhVideo.currentTime / kisskhVideo.duration) * 100 || 0;
                }
                timeDisplay.textContent = formatTime(kisskhVideo.currentTime) + ' / ' + formatTime(kisskhVideo.duration);
            }

            function updateBuffer() {
                if (kisskhVideo.buffered.length > 0) {
                    var bufferedEnd = kisskhVideo.buffered.end(kisskhVideo.buffered.length - 1);
                    var pct = (bufferedEnd / kisskhVideo.duration) * 100 || 0;
                    bufferBar.style.width = pct + '%';
                }
            }

            function updateQuality() {
                if (hls && hls.levels && hls.levels.length > 0) {
                    var level = hls.currentLevel;
                    if (level >= 0 && hls.levels[level]) {
                        var h = hls.levels[level].height || 0;
                        if (h >= 1080) qualityDisplay.textContent = '1080p';
                        else if (h >= 720) qualityDisplay.textContent = '720p';
                        else if (h >= 480) qualityDisplay.textContent = '480p';
                        else if (h >= 360) qualityDisplay.textContent = '360p';
                        else qualityDisplay.textContent = h + 'p';
                    }
                }
            }

            function showControls() {
                controlsEl.classList.add('visible');
                clearTimeout(controlsTimeout);
            }

            function hideControls() {
                if (!kisskhVideo.paused) {
                    controlsEl.classList.remove('visible');
                }
            }

            function resetControlsTimer() {
                showControls();
                controlsTimeout = setTimeout(hideControls, 3000);
            }

            // Play/Pause
            playBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                kisskhVideo.focus();
                if (kisskhVideo.paused) {
                    kisskhVideo.play().catch(function () {});
                } else {
                    kisskhVideo.pause();
                }
                resetControlsTimer();
            });

            // Click video to toggle play/pause
            kisskhVideo.addEventListener('click', function () {
                if (kisskhVideo.paused) {
                    kisskhVideo.play().catch(function () {});
                } else {
                    kisskhVideo.pause();
                }
            });

            // Seek
            seekBar.addEventListener('input', function () {
                isSeeking = true;
                var pct = parseFloat(seekBar.value) / 100;
                if (isFinite(kisskhVideo.duration)) {
                    var t = pct * kisskhVideo.duration;
                    if (!isNaN(t)) timeDisplay.textContent = formatTime(t) + ' / ' + formatTime(kisskhVideo.duration);
                }
            });
            seekBar.addEventListener('change', function () {
                var pct = parseFloat(seekBar.value) / 100;
                if (!isFinite(kisskhVideo.duration)) return;
                kisskhVideo.currentTime = pct * kisskhVideo.duration;
                isSeeking = false;
                resetControlsTimer();
            });

            // Volume
            volumeBar.addEventListener('input', function () {
                kisskhVideo.volume = parseFloat(volumeBar.value);
                kisskhVideo.muted = kisskhVideo.volume === 0;
                updateVolumeBtn();
            });
            volumeBtn.addEventListener('click', function () {
                kisskhVideo.muted = !kisskhVideo.muted;
                updateVolumeBtn();
                if (!kisskhVideo.muted) volumeBar.value = kisskhVideo.volume;
            });
            function updateVolumeBtn() {
                var icon = 'bi-volume-up-fill';
                if (kisskhVideo.muted || kisskhVideo.volume === 0) icon = 'bi-volume-mute-fill';
                else if (kisskhVideo.volume < 0.5) icon = 'bi-volume-down-fill';
                volumeBtn.innerHTML = '<i class="bi ' + icon + '"></i>';
            }

            // Rewind / Forward
            rewindBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                if (!kisskhVideo || !isFinite(kisskhVideo.duration)) return;
                kisskhVideo.currentTime = Math.max(0, kisskhVideo.currentTime - 10);
                resetControlsTimer();
            });
            forwardBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                if (!kisskhVideo || !isFinite(kisskhVideo.duration)) return;
                kisskhVideo.currentTime = Math.min(kisskhVideo.duration, kisskhVideo.currentTime + 10);
                resetControlsTimer();
            });

            // Fullscreen
            fullscreenBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                var fsEl = document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement;
                if (!fsEl) {
                    var el = playerContainer;
                    var req = el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen || el.msRequestFullscreen;
                    if (req) {
                        req.call(el).catch(function () {});
                    }
                } else {
                    var exit = document.exitFullscreen || document.webkitExitFullscreen || document.mozCancelFullScreen || document.msExitFullscreen;
                    if (exit) exit.call(document).catch(function () {});
                }
            });
            function updateFsBtn() {
                var fsEl = document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement;
                var icon = fsEl ? 'bi-fullscreen-exit' : 'bi-fullscreen';
                fullscreenBtn.innerHTML = '<i class="bi ' + icon + '"></i>';
            }
            document.addEventListener('fullscreenchange', updateFsBtn);
            document.addEventListener('webkitfullscreenchange', updateFsBtn);
            document.addEventListener('mozfullscreenchange', updateFsBtn);
            document.addEventListener('MSFullscreenChange', updateFsBtn);

            // Keyboard shortcuts (global)
            document.addEventListener('keydown', function (e) {
                // Ignore if typing in input/textarea
                var tag = e.target.tagName;
                if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
                if (!kisskhVideo || !kisskhVideo.duration) return;
                if (e.key === ' ' || e.key === 'k') {
                    e.preventDefault();
                    playBtn.click();
                }
                if (e.key === 'f') {
                    e.preventDefault();
                    fullscreenBtn.click();
                }
                if (e.key === 'm') {
                    e.preventDefault();
                    volumeBtn.click();
                }
                if (e.key === 'ArrowLeft') {
                    e.preventDefault();
                    rewindBtn.click();
                }
                if (e.key === 'ArrowRight') {
                    e.preventDefault();
                    forwardBtn.click();
                }
                if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    var v = Math.min(1, kisskhVideo.volume + 0.1);
                    kisskhVideo.volume = v;
                    kisskhVideo.muted = false;
                    volumeBar.value = v;
                    updateVolumeBtn();
                }
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    var v = Math.max(0, kisskhVideo.volume - 0.1);
                    kisskhVideo.volume = v;
                    if (v === 0) kisskhVideo.muted = true;
                    volumeBar.value = v;
                    updateVolumeBtn();
                }
            });

            // Video events
            kisskhVideo.addEventListener('play', function () {
                updatePlayBtn();
                playerContainer.classList.remove('paused');
                resetControlsTimer();
            });
            kisskhVideo.addEventListener('pause', function () {
                updatePlayBtn();
                playerContainer.classList.add('paused');
                showControls();
                clearTimeout(controlsTimeout);
            });
            kisskhVideo.addEventListener('ended', function () {
                updatePlayBtn();
                playerContainer.classList.add('video-ended');
                showControls();
                playBtn.innerHTML = '<i class="bi bi-arrow-repeat"></i>';
            });
            kisskhVideo.addEventListener('timeupdate', function () {
                updateTime();
                updateBuffer();
            });
            kisskhVideo.addEventListener('loadedmetadata', function () {
                timeDisplay.textContent = '0:00 / ' + formatTime(kisskhVideo.duration);
                seekBar.max = 100;
            });
            kisskhVideo.addEventListener('progress', updateBuffer);
            kisskhVideo.addEventListener('volumechange', updateVolumeBtn);

            // HLS quality tracking
            if (hls) {
                hls.on(Hls.Events.LEVEL_SWITCHED, function () {
                    updateQuality();
                });
            }

            // Mouse move on player shows controls
            playerContainer.addEventListener('mousemove', function () {
                resetControlsTimer();
            });
            playerContainer.addEventListener('mouseleave', function () {
                if (!kisskhVideo.paused) {
                    controlsTimeout = setTimeout(hideControls, 1500);
                }
            });
            controlsEl.addEventListener('mouseenter', showControls);
            controlsEl.addEventListener('mouseleave', function () {
                if (!kisskhVideo.paused) {
                    controlsTimeout = setTimeout(hideControls, 1500);
                }
            });

            // Touch: tap to toggle controls
            var touchTimer;
            playerContainer.addEventListener('touchstart', function () {
                if (controlsEl.classList.contains('visible')) {
                    controlsEl.classList.remove('visible');
                    clearTimeout(touchTimer);
                } else {
                    controlsEl.classList.add('visible');
                    clearTimeout(touchTimer);
                    touchTimer = setTimeout(function () {
                        if (!kisskhVideo.paused) controlsEl.classList.remove('visible');
                    }, 4000);
                }
            });

            // Init
            updatePlayBtn();
            updateVolumeBtn();
            updateTime();
            showControls();
            controlsTimeout = setTimeout(hideControls, 3000);
        }
    }

    // ========== DETAIL PAGE: Source Switching + Proxy ==========
    var currentBase = $('.source-btn.btn-kdrama').data('base') || $('#mainEmbed').attr('src');
    var currentFmt = $('.source-btn.btn-kdrama').data('fmt');

    $('.source-btn').on('click', function () {
        $('.source-btn').removeClass('btn-kdrama').addClass('btn-outline-secondary');
        $(this).removeClass('btn-outline-secondary').addClass('btn-kdrama');
        currentBase = $(this).data('base');
        currentFmt = $(this).data('fmt');
        reloadPlayer();
    });

    // Only bind regular proxy toggle if NOT on KissKh page
    if (typeof kisskhEpisodes === 'undefined') {
        $('input[name="proxyMode"]').on('change', function () {
            reloadPlayer();
        });
    }

    function reloadPlayer() {
        var embed = $('#mainEmbed');
        var imdb = embed.data('imdb');
        var type = embed.data('type');
        var season = $('#seasonSelect').val();
        var episode = $('#episodeSelect').val();
        var useProxy = $('input[name="proxyMode"]:checked').val() === 'on';

        var src = buildEmbedUrl(currentBase, currentFmt, imdb, type, season, episode);

        if (useProxy) {
            var proxyUrl = '/proxy/embed/' + src.replace('https://', '');
            embed.attr('src', proxyUrl);
        } else {
            embed.attr('src', src);
        }
    }

    function buildEmbedUrl(base, fmt, imdb, type, season, episode) {
        if (fmt === 'flat') {
            return base;
        }
        if (fmt === 'path') {
            if (base.indexOf('/' + imdb) >= 0) {
                return base + '/' + (season || 1) + '-' + (episode || 1);
            }
            return base + '/' + imdb + '/' + (season || 1) + '-' + (episode || 1);
        }
        if (type === 'movie') {
            return base + '?imdb=' + imdb;
        }
        return base + '?imdb=' + imdb + '&season=' + (season || 1) + '&episode=' + (episode || 1);
    }

    $('#loadEpisodeBtn').on('click', function () {
        reloadPlayer();
    });

    // ========== LANDING PAGE: LOAD LATEST ==========
    if ($('#latestMovies').length) {
        loadGrid('movie', 1, '#latestMovies');
        loadGrid('tv', 1, '#latestTVShows');
    }

    function loadGrid(type, page, container) {
        var url = '/api/latest/' + type;
        $.getJSON(url, function (data) {
            var items = data.result || [];
            $(container).empty();

            if (items.length === 0) {
                $(container).html('<div class="col-12 text-center text-muted py-4">No content available.</div>');
                return;
            }

            $.each(items, function (i, item) {
                var card = buildCard(item, type);
                $(container).append(card);
            });
        }).fail(function () {
            $(container).html('<div class="col-12 text-center text-muted py-4">Failed to load. Try again later.</div>');
        });
    }

    function buildCard(item, type) {
        var color = item.color || '#e74c6f';
        var initials = (item.title || '?').charAt(0).toUpperCase();
        var hasPoster = item.poster || item.thumbnail;

        var poster = hasPoster
            ? '<img src="' + (item.poster || item.thumbnail) + '" class="card-img-top" alt="' + escapeHtml(item.title) + '" loading="lazy">'
            : '<div class="placeholder-poster d-flex align-items-center justify-content-center" style="background:' + color + '20;position:relative;">'
            + '<span style="font-size:3rem;font-weight:700;color:' + color + ';">' + initials + '</span>'
            + '<span class="play-icon"><i class="bi bi-play-circle-fill" style="font-size:2rem;color:' + color + ';opacity:0.6;"></i></span>'
            + '</div>';

        var episodes = item.episodes_count ? '<span class="badge bg-secondary me-1">' + item.episodes_count + ' ep</span>' : '';
        var link = '/detail/kisskh/' + item.kisskh_id;

        return '<div class="col-6 col-md-4 col-lg-3 col-xl-2">'
            + '<a href="' + link + '" class="text-decoration-none">'
            + '<div class="card-movie" style="position:relative;">'
            + poster
            + '<div class="card-body">'
            + '<div class="card-title text-light">' + escapeHtml(item.title) + '</div>'
            + '<div>' + episodes + '</div>'
            + '</div></div></a></div>';
    }

    // ========== BROWSE PAGE ==========
    var browseType = getParam('type') || 'movie';
    var browseQuery = getParam('q') || '';
    var browseKeywords = ['a', 'e', 'ko', '2025', '2026', 'love', 'man', 'king', 'day', 'night'];
    var browseKwdIdx = 0;
    var loading = false;
    var allLoaded = false;
    var currentGenre = '';

    function loadBrowse(append) {
        if (loading || allLoaded) return;
        loading = true;

        var url;
        if (browseQuery) {
            url = '/api/kisskh/search?q=' + encodeURIComponent(browseQuery) + '&type=' + browseType;
        } else if (currentGenre) {
            url = '/api/kisskh/search?q=' + encodeURIComponent(currentGenre) + '&type=' + browseType;
        } else {
            url = '/api/kisskh/search?q=' + encodeURIComponent(browseKeywords[browseKwdIdx % browseKeywords.length]) + '&type=' + browseType;
            browseKwdIdx++;
        }

        if (!append) $('#browseGrid').empty().append('<div class="col-12 text-center py-5"><div class="spinner-border text-kdrama"></div></div>');

        $.getJSON(url, function (data) {
            var items = data.result || [];
            if (!append) $('#browseGrid').empty();

            if (items.length === 0 && !browseQuery && !currentGenre) {
                if (browseKwdIdx < browseKeywords.length * 2) {
                    loading = false;
                    loadBrowse(append);
                    return;
                }
                $('#browseGrid').html('<div class="col-12 text-center text-muted py-5">No results found.</div>');
                $('#loadMoreBtn').hide();
                loading = false;
                return;
            }

            $.each(items, function (i, item) {
                var card = buildCard(item, browseType);
                $('#browseGrid').append(card);
            });

            if (items.length === 0) {
                $('#loadMoreBtn').hide();
                loading = false;
                if (!append && $('#browseGrid').children().length === 0) {
                    $('#browseGrid').html('<div class="col-12 text-center text-muted py-5">No results found.</div>');
                }
                return;
            }

            if (!browseQuery && !currentGenre && browseKwdIdx < browseKeywords.length) {
                $('#loadMoreBtn').show();
            } else {
                $('#loadMoreBtn').hide();
                allLoaded = true;
            }
            loading = false;
        }).fail(function () {
            $('#browseGrid').html('<div class="col-12 text-center text-muted py-5">Failed to load content.</div>');
            loading = false;
        });
    }

    if ($('#browseGrid').length) {
        loadBrowse(false);

        $('#loadMoreBtn').on('click', function () {
            loadBrowse(true);
        });

        $('#searchBtn').on('click', function () {
            browseQuery = $('#searchInput').val().trim();
            currentGenre = '';
            $('#genreFilters .genre-btn').removeClass('active').first().addClass('active');
            browseKwdIdx = 0;
            allLoaded = false;
            loadBrowse(false);
        });

        $('#searchInput').on('keypress', function (e) {
            if (e.which === 13) $('#searchBtn').click();
        });

        $('#genreFilters').on('click', '.genre-btn', function () {
            var genre = $(this).data('genre');
            if (genre === currentGenre) return;
            currentGenre = genre;
            $('#genreFilters .genre-btn').removeClass('active');
            $(this).addClass('active');
            browseQuery = '';
            $('#searchInput').val('');
            browseKwdIdx = 0;
            allLoaded = false;
            loadBrowse(false);
        });
    }

    // ========== HELPERS ==========
    function getParam(name) {
        name = name.replace(/[\[\]]/g, '\\$&');
        var regex = new RegExp('[?&]' + name + '(=([^&#]*)|&|#|$)');
        var results = regex.exec(window.location.href);
        if (!results) return null;
        if (!results[2]) return '';
        return decodeURIComponent(results[2].replace(/\+/g, ' '));
    }

    function getParamFromUrl(url, name) {
        name = name.replace(/[\[\]]/g, '\\$&');
        var regex = new RegExp('[?&]' + name + '(=([^&#]*)|&|#|$)');
        var results = regex.exec(url);
        if (!results) return '';
        if (!results[2]) return '';
        return decodeURIComponent(results[2].replace(/\+/g, ' '));
    }

    function escapeHtml(text) {
        if (!text) return '';
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

});
