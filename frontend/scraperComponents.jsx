// Screenscraper and IGDB Integration Components
// To be imported into the main React application

export const ScraperSearchPopup = ({ 
  isOpen, 
  onClose, 
  gameData,
  onApplyMetadata 
}) => {
  const [searchQuery, setSearchQuery] = React.useState(gameData?.name || '');
  const [searchResults, setSearchResults] = React.useState([]);
  const [selectedResult, setSelectedResult] = React.useState(null);
  const [scraperMetadata, setScraperMetadata] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [selectedFields, setSelectedFields] = React.useState({});
  const [selectedMediaTypes, setSelectedMediaTypes] = React.useState({});
  const [showComparison, setShowComparison] = React.useState(false);
  const [downloadingMedia, setDownloadingMedia] = React.useState(false);
  const [activeSource, setActiveSource] = React.useState('screenscraper'); // 'screenscraper' or 'igdb'
  const [currentSource, setCurrentSource] = React.useState(null); // Track which source results are from

  // Update search query when gameData changes
  React.useEffect(() => {
    if (gameData?.name) {
      setSearchQuery(gameData.name);
      setSearchResults([]);
      setSelectedResult(null);
      setScraperMetadata(null);
      setShowComparison(false);
      setActiveSource('screenscraper');
      setCurrentSource(null);
    }
  }, [gameData?.name]);

  if (!isOpen) return null;

  const handleSearch = async (source) => {
    if (!searchQuery.trim()) return;

    setLoading(true);
    setActiveSource(source);
    try {
      let endpoint = '/api/scraper/search';
      let body = { 
        name: searchQuery,
        system_id: null
      };

      if (source === 'igdb') {
        endpoint = '/api/igdb/search';
        body = {
          name: searchQuery,
          system_name: gameData?.system || null
        };
      }

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await response.json();
      if (data.success) {
        setSearchResults(data.results);
        setCurrentSource(source);
        setSelectedResult(null);
        setScraperMetadata(null);
      } else {
        setSearchResults([]);
        setSelectedResult(null);
        setScraperMetadata(null);
        setCurrentSource(null);
        console.error('Search error:', data.error);
        alert(`Search failed: ${data.error || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Search failed:', error);
      alert(`Search failed: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectResult = async (result) => {
    setSelectedResult(result);
    setLoading(true);
    try {
      let endpoint = '/api/scraper/game-info';
      let body = {
        game_id: result.id,
        system_id: result.systemeid
      };

      if (currentSource === 'igdb') {
        endpoint = '/api/igdb/game-info';
        body = { game_id: result.id };
      }

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await response.json();
      if (data.success) {
        setScraperMetadata(data.metadata);
        setShowComparison(true);
        // Initialize all fields as selected by default
        const fields = {};
        Object.keys(data.metadata).forEach(key => {
          if (key !== 'media') {
            fields[key] = true;
          }
        });
        setSelectedFields(fields);
      }
    } catch (error) {
      console.error('Failed to fetch game info:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleFieldToggle = (field) => {
    setSelectedFields(prev => ({
      ...prev,
      [field]: !prev[field]
    }));
  };

  const getSourceLabel = () => {
    if (currentSource === 'igdb') return 'IGDB';
    if (currentSource === 'screenscraper') return 'ScreenScraper';
    return 'Search Results';
  };

  const handleMediaToggle = (mediaType) => {
    setSelectedMediaTypes(prev => ({
      ...prev,
      [mediaType]: !prev[mediaType]
    }));
  };

  const handleApplyAll = () => {
    const fields = {};
    Object.keys(scraperMetadata).forEach(key => {
      if (key !== 'media') {
        fields[key] = true;
      }
    });
    setSelectedFields(fields);
  };

  const handleSelectAllMedia = () => {
    const media = scraperMetadata?.media || {};
    const allMedia = {};
    Object.keys(media).forEach(key => {
      allMedia[key] = true;
    });
    setSelectedMediaTypes(allMedia);
  };

  const handleDownloadMedia = async () => {
    const media = scraperMetadata?.media || {};
    const mediaToDownload = {};
    
    Object.entries(selectedMediaTypes).forEach(([type, isSelected]) => {
      if (isSelected && media[type]) {
        mediaToDownload[type] = media[type];
      }
    });
    
    if (Object.keys(mediaToDownload).length === 0) {
      alert('Please select at least one media type to download');
      return;
    }
    
    setDownloadingMedia(true);
    try {
      const response = await fetch('/api/scraper/download-media', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          system_name: gameData.system || 'unknown',
          game_name: gameData.name,
          media_types: mediaToDownload
        })
      });
      
      const result = await response.json();
      if (result.success) {
        const count = Object.keys(result.saved_media).length;
        alert(`Successfully downloaded ${count} media file(s)`);
        if (result.errors && result.errors.length > 0) {
          console.warn('Some media downloads had errors:', result.errors);
        }
      } else {
        alert(`Failed to download media: ${result.error}`);
      }
    } catch (error) {
      console.error('Media download failed:', error);
      alert(`Media download failed: ${error.message}`);
    } finally {
      setDownloadingMedia(false);
    }
  };

  const handleApplySelected = async () => {
    const mergedMetadata = { ...gameData };
    Object.entries(selectedFields).forEach(([field, isSelected]) => {
      if (isSelected && scraperMetadata[field]) {
        mergedMetadata[field] = scraperMetadata[field];
      }
    });
    
    // Download media if any are selected
    if (Object.values(selectedMediaTypes).some(v => v)) {
      await handleDownloadMedia();
    }
    
    onApplyMetadata(mergedMetadata);
    onClose();
  };

  const renderComparisonField = (field) => {
    const current = gameData?.[field] || '(empty)';
    const scraped = scraperMetadata?.[field] || '(empty)';
    
    return (
      <div key={field} style={styles.comparisonField}>
        <div style={styles.fieldCheckbox}>
          <input
            type="checkbox"
            checked={selectedFields[field] || false}
            onChange={() => handleFieldToggle(field)}
          />
        </div>
        <div style={styles.fieldName}>{field}</div>
        <div style={styles.currentValue}>
          <strong>Current:</strong>
          <div style={styles.value}>{current}</div>
        </div>
        <div style={styles.scrapedValue}>
          <strong>Scraped:</strong>
          <div style={styles.value}>{scraped}</div>
        </div>
      </div>
    );
  };

  const renderMediaSelection = () => {
    const media = scraperMetadata?.media || {};
    const mediaTypes = Object.keys(media);
    
    if (mediaTypes.length === 0) {
      return (
        <div style={styles.mediaSection}>
          <h4>Media Available</h4>
          <div style={styles.noMedia}>No media available for this game</div>
        </div>
      );
    }
    
    return (
      <div style={styles.mediaSection}>
        <div style={styles.mediaSectionHeader}>
          <h4>Media Available ({mediaTypes.length})</h4>
          <button onClick={handleSelectAllMedia} style={styles.selectAllMediaBtn}>
            Select All Media
          </button>
        </div>
        <div style={styles.mediaGrid}>
          {mediaTypes.map(type => (
            <div key={type} style={styles.mediaItem}>
              <input
                type="checkbox"
                checked={selectedMediaTypes[type] || false}
                onChange={() => handleMediaToggle(type)}
                id={`media-${type}`}
              />
              <label htmlFor={`media-${type}`} style={styles.mediaLabel}>
                {type}
              </label>
              {media[type] && (
                <a 
                  href={media[type]} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  style={styles.mediaLink}
                  title="Preview in new tab"
                >
                  Preview →
                </a>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div style={styles.header}>
          <h2>Game Metadata Search</h2>
          <button onClick={onClose} style={styles.closeBtn}>×</button>
        </div>

        {!showComparison ? (
          <div style={styles.content}>
            <div style={styles.searchContainer}>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search game name..."
                style={styles.searchInput}
              />
              <div style={styles.searchButtonGroup}>
                <button 
                  onClick={() => handleSearch('screenscraper')} 
                  disabled={loading}
                  style={{
                    ...styles.searchBtn,
                    ...styles.searchBtnScreenscraper,
                    ...(activeSource === 'screenscraper' && !loading ? styles.searchBtnActive : {})
                  }}
                  title="Search on ScreenScraper.fr"
                >
                  <span style={styles.searchBtnLogo}>🎮</span>
                  Search ScreenScraper
                </button>
                <button 
                  onClick={() => handleSearch('igdb')} 
                  disabled={loading}
                  style={{
                    ...styles.searchBtn,
                    ...styles.searchBtnIGDB,
                    ...(activeSource === 'igdb' && !loading ? styles.searchBtnActive : {})
                  }}
                  title="Search on IGDB"
                >
                  <span style={styles.searchBtnLogo}>📊</span>
                  Search IGDB
                </button>
              </div>
            </div>

            {searchResults.length > 0 && (
              <div style={styles.sourceLabel}>
                Results from: <strong>{getSourceLabel()}</strong>
              </div>
            )}

            <div style={styles.resultsList}>
              {searchResults.map((result) => {
                const displayName = result.nom || result.name;
                const displaySystem = result.systemenom || (result.platforms ? result.platforms.join(', ') : '');
                const displayImage = result.image || result.cover_url;
                
                return (
                  <div
                    key={result.id}
                    onClick={() => handleSelectResult(result)}
                    style={{
                      ...styles.resultItem,
                      ...(selectedResult?.id === result.id ? styles.resultItemSelected : {})
                    }}
                  >
                    {displayImage && (
                      <img src={displayImage} alt={displayName} style={styles.resultImage} />
                    )}
                    <div style={styles.resultInfo}>
                      <div style={styles.resultName}>{displayName}</div>
                      <div style={styles.resultSystem}>{displaySystem}</div>
                    </div>
                  </div>
                );
              })}
            </div>

            {!loading && searchResults.length === 0 && currentSource && (
              <div style={styles.noResults}>
                No results found. Try a different search term or source.
              </div>
            )}
          </div>
        ) : (
          <div style={styles.content}>
            <div style={styles.comparisonHeader}>
              <h3>Compare Metadata</h3>
              <button onClick={() => setShowComparison(false)} style={styles.backBtn}>
                ← Back to Search
              </button>
            </div>

            <div style={styles.selectedGame}>
              <strong>Selected ({getSourceLabel()}):</strong> {selectedResult?.nom || selectedResult?.name}
            </div>

            <div style={styles.fieldsActions}>
              <button onClick={handleApplyAll} style={styles.actionBtn}>
                Select All Fields
              </button>
              <button onClick={() => setSelectedFields({})} style={styles.actionBtn}>
                Deselect All
              </button>
            </div>

            <div style={styles.fieldsContainer}>
              {Object.keys(scraperMetadata)
                .filter(key => key !== 'media')
                .map(field => renderComparisonField(field))
              }
            </div>

            {renderMediaSelection()}

            <div style={styles.footer}>
              <button onClick={onClose} style={styles.cancelBtn}>Cancel</button>
              <button 
                onClick={handleApplySelected} 
                disabled={downloadingMedia}
                style={styles.applyBtn}
              >
                {downloadingMedia ? 'Downloading Media...' : 'Apply Selected Changes'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const styles = {
  overlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
  },
  modal: {
    backgroundColor: '#0f1535',
    borderRadius: '8px',
    border: '1px solid #2a2d4a',
    maxWidth: '900px',
    width: '90%',
    maxHeight: '90vh',
    display: 'flex',
    flexDirection: 'column',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '20px',
    borderBottom: '1px solid #2a2d4a',
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: '#e0e0e0',
    fontSize: '28px',
    cursor: 'pointer',
  },
  content: {
    flex: 1,
    overflow: 'auto',
    padding: '20px',
  },
  searchContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    marginBottom: '20px',
  },
  searchInput: {
    padding: '12px',
    backgroundColor: '#14194f',
    border: '1px solid #2a2d4a',
    color: '#e0e0e0',
    borderRadius: '4px',
    fontSize: '14px',
  },
  searchButtonGroup: {
    display: 'flex',
    gap: '10px',
  },
  searchBtn: {
    flex: 1,
    padding: '12px 16px',
    border: '1px solid #2a2d4a',
    borderRadius: '4px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    fontSize: '14px',
    fontWeight: '500',
    transition: 'all 0.2s',
  },
  searchBtnScreenscraper: {
    backgroundColor: '#1a1f5a',
    color: '#e0e0e0',
    borderColor: '#ff6b9d',
  },
  searchBtnIGDB: {
    backgroundColor: '#1a1f5a',
    color: '#e0e0e0',
    borderColor: '#6b5dd0',
  },
  searchBtnActive: {
    backgroundColor: '#2a2d4a',
    borderColor: '#fff',
  },
  searchBtnLogo: {
    fontSize: '18px',
  },
  sourceLabel: {
    padding: '10px',
    backgroundColor: '#14194f',
    borderLeft: '3px solid #ff6b9d',
    borderRadius: '4px',
    marginBottom: '15px',
    color: '#e0e0e0',
    fontSize: '13px',
  },
  resultsList: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))',
    gap: '15px',
  },
  resultItem: {
    backgroundColor: '#14194f',
    border: '1px solid #2a2d4a',
    borderRadius: '4px',
    padding: '10px',
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  resultItemSelected: {
    borderColor: '#ff6b9d',
    backgroundColor: '#1a1f5a',
  },
  resultImage: {
    width: '100%',
    height: '150px',
    objectFit: 'cover',
    borderRadius: '4px',
    marginBottom: '10px',
    backgroundColor: '#0f1535',
  },
  resultInfo: {
    padding: '5px',
  },
  resultName: {
    color: '#e0e0e0',
    fontWeight: 'bold',
    fontSize: '14px',
    marginBottom: '5px',
  },
  resultSystem: {
    color: '#999999',
    fontSize: '12px',
  },
  noResults: {
    textAlign: 'center',
    color: '#999999',
    padding: '40px 20px',
    fontSize: '14px',
  },
  comparisonHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '20px',
  },
  backBtn: {
    padding: '8px 12px',
    backgroundColor: '#6b5dd0',
    color: '#fff',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
  },
  selectedGame: {
    backgroundColor: '#14194f',
    padding: '10px',
    borderRadius: '4px',
    marginBottom: '15px',
    color: '#e0e0e0',
    fontSize: '13px',
  },
  fieldsActions: {
    display: 'flex',
    gap: '10px',
    marginBottom: '15px',
  },
  actionBtn: {
    padding: '8px 12px',
    backgroundColor: '#ff9d3d',
    color: '#fff',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '13px',
  },
  fieldsContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: '15px',
    marginBottom: '20px',
  },
  comparisonField: {
    display: 'grid',
    gridTemplateColumns: '40px 150px 1fr 1fr',
    gap: '15px',
    backgroundColor: '#14194f',
    padding: '15px',
    borderRadius: '4px',
    alignItems: 'start',
  },
  fieldCheckbox: {
    display: 'flex',
    alignItems: 'center',
  },
  fieldName: {
    fontWeight: 'bold',
    color: '#ff6b9d',
    wordBreak: 'break-word',
  },
  currentValue: {
    backgroundColor: '#0f1535',
    padding: '10px',
    borderRadius: '4px',
  },
  scrapedValue: {
    backgroundColor: '#0f1535',
    padding: '10px',
    borderRadius: '4px',
  },
  value: {
    color: '#e0e0e0',
    marginTop: '5px',
    fontSize: '12px',
    wordBreak: 'break-word',
  },
  footer: {
    display: 'flex',
    justifyContent: 'flex-end',
    gap: '10px',
    padding: '20px',
    borderTop: '1px solid #2a2d4a',
  },
  cancelBtn: {
    padding: '10px 20px',
    backgroundColor: '#2a2d4a',
    color: '#e0e0e0',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
  },
  applyBtn: {
    padding: '10px 20px',
    backgroundColor: '#ff6b9d',
    color: '#fff',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
  },
  mediaSection: {
    backgroundColor: '#14194f',
    padding: '15px',
    borderRadius: '4px',
    marginBottom: '15px',
    borderLeft: '3px solid #ff9d3d',
  },
  mediaSectionHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '15px',
  },
  selectAllMediaBtn: {
    padding: '6px 12px',
    backgroundColor: '#ff9d3d',
    color: '#fff',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '12px',
  },
  mediaGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
    gap: '10px',
  },
  mediaItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px',
    backgroundColor: '#0f1535',
    borderRadius: '4px',
    wordBreak: 'break-word',
  },
  mediaLabel: {
    flex: 1,
    color: '#e0e0e0',
    cursor: 'pointer',
    fontSize: '13px',
  },
  mediaLink: {
    color: '#6b5dd0',
    textDecoration: 'none',
    fontSize: '11px',
    whiteSpace: 'nowrap',
  },
  noMedia: {
    color: '#999999',
    padding: '10px',
    textAlign: 'center',
    fontSize: '13px',
  },
};
