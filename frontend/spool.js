(() => {
  const $ = (id) => document.getElementById(id);
  const state = { url: '', isPlaylist: false, tab: 'video', qualities: [] };
  const urlInput = $('urlInput'), loadBtn = $('loadBtn'), errorBanner = $('errorBanner');

  const apiBase = () => $('apiBase').value.trim().replace(/\/$/, '');
  const showError = (message) => { errorBanner.textContent = message; errorBanner.hidden = false; };
  const clearError = () => { errorBanner.hidden = true; };
  const isPlaylistUrl = (url) => /[?&]list=[^&]+/.test(url) || /youtube\.com\/playlist/.test(url);

  document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((item) => item.classList.toggle('active', item === tab));
    state.tab = tab.dataset.tab;
    $('videoPanel').hidden = state.tab !== 'video';
    $('audioPanel').hidden = state.tab !== 'audio';
  }));

  loadBtn.addEventListener('click', load);
  urlInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') load(); });

  async function load() {
    clearError();
    const url = urlInput.value.trim();
    if (!/^https?:\/\//.test(url) || !/youtu/.test(url)) return showError('Paste a valid YouTube video or playlist link.');
    state.url = url; state.isPlaylist = isPlaylistUrl(url);
    loadBtn.disabled = true; loadBtn.textContent = '…';
    try {
      const response = await fetch(`${apiBase()}/formats?url=${encodeURIComponent(url)}`);
      if (!response.ok) throw new Error(`Server responded ${response.status}`);
      const data = await response.json();
      const isPlaylist = state.isPlaylist || data._type === 'playlist' || Array.isArray(data.entries);
      state.isPlaylist = isPlaylist;
      $('contentType').textContent = isPlaylist ? 'PLAYLIST → ZIP' : 'VIDEO';
      $('contentTitle').textContent = data.title || (isPlaylist ? 'YouTube playlist' : 'YouTube video');
      $('contentMeta').textContent = isPlaylist ? 'Every available item will be packed into a ZIP download.' : (data.uploader || 'Ready to download');
      $('previewSection').hidden = false;
      populateQualities(data.video_qualities || []);
      $('optionsSection').hidden = false;
    } catch (error) {
      showError(`Could not load this link: ${error.message}. Make sure the API is running at ${apiBase()}.`);
    } finally { loadBtn.disabled = false; loadBtn.textContent = 'LOAD'; }
  }

  function populateQualities(qualities) {
    const select = $('qualitySelect'); select.innerHTML = '';
    qualities.forEach((quality) => {
      const option = document.createElement('option');
      option.value = quality.format_id || ''; option.textContent = quality.label || quality.resolution || 'Best available';
      option.dataset.height = quality.height || ''; option.dataset.codec = quality.codec_family || '';
      select.appendChild(option);
    });
    if (!select.options.length) select.add(new Option('Best available', ''));
  }

  $('downloadBtn').addEventListener('click', async () => {
    if (!state.url) return showError('Load a link first.');
    clearError(); const button = $('downloadBtn'); button.disabled = true;
    $('progressSection').hidden = false; $('progressBar').style.width = '12%'; $('progressStatus').textContent = 'The server is preparing your file…';
    const params = new URLSearchParams({ url: state.url });
    if (state.isPlaylist) {
      params.set('media_type', state.tab === 'video' ? 'mp4' : 'audio');
      if (state.tab === 'audio') { params.set('audio_format', $('audioFormat').value); params.set('bitrate', $('audioBitrate').value); }
    } else if (state.tab === 'video') {
      const selected = $('qualitySelect').selectedOptions[0];
      if (selected.value) params.set('format_id', selected.value);
    } else { params.set('audio_format', $('audioFormat').value); params.set('bitrate', $('audioBitrate').value); }
    const endpoint = state.isPlaylist ? '/download/playlist' : state.tab === 'video' ? '/download/mp4' : '/download/audio';
    try {
      const response = await fetch(`${apiBase()}${endpoint}?${params}`);
      if (!response.ok) throw new Error(`Server responded ${response.status}`);
      const blob = await response.blob(); $('progressBar').style.width = '100%';
      const disposition = response.headers.get('Content-Disposition') || '';
      const name = (disposition.match(/filename="?([^";]+)"?/) || [])[1] || (state.isPlaylist ? 'playlist.zip' : 'download');
      const anchor = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: name });
      anchor.click(); $('progressStatus').textContent = `Saved ${name}.`;
    } catch (error) { $('progressSection').hidden = true; showError(`Download failed: ${error.message}`); }
    finally { button.disabled = false; }
  });
})();
