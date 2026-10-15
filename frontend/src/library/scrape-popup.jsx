// The Scrape popup: search a source, compare its metadata, assign its media.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

// Scrape popup: search a source, compare its metadata, assign its media
const ScraperSearchPopup = ({ 
    isOpen, 
    onClose, 
    gameData,
    systemName,
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
    const [activeSource, setActiveSource] = React.useState('screenscraper');
    const [currentSource, setCurrentSource] = React.useState(null);
    const [metadataSource, setMetadataSource] = React.useState(null);
    const [imageAssignments, setImageAssignments] = React.useState({});
    const [previewImage, setPreviewImage] = React.useState(null);
    const previewRef = React.useRef(null);
    // Bring the full-size preview into view when it opens (it sits above the cards)
    React.useEffect(() => {
        if (previewImage && previewRef.current) previewRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }, [previewImage]);
    // Message shown inside the popup: {type: 'error' | 'info', text}
    const [message, setMessage] = React.useState(null);
    // Download progress: {done, total, current}
    const [progress, setProgress] = React.useState(null);
    // Set once changes are applied but some downloads failed, so the popup stays open to show why
    const [appliedWithErrors, setAppliedWithErrors] = React.useState(false);
    // Which sources the server can use: {id: {available, hint}}. Until it
    // answers (or if it's an older server) every source is offered.
    const [sourceStatus, setSourceStatus] = React.useState({});

    // Each time the popup opens, start without old messages or progress
    React.useEffect(() => {
        if (isOpen) {
            setMessage(null);
            setAppliedWithErrors(false);
            setProgress(null);
            fetch('/api/scrape-sources').then(r => r.json()).then(d => {
                if (d.success) setSourceStatus(Object.fromEntries(d.sources.map(src => [src.id, src])));
            }).catch(() => {});
        }
    }, [isOpen]);

    // Update search query when gameData changes
    React.useEffect(() => {
        if (gameData?.name) {
            setSearchQuery(gameData.name);
            setMessage(null);
            setAppliedWithErrors(false);
            setSearchResults([]);
            setSelectedResult(null);
            setScraperMetadata(null);
            setMetadataSource(null);
            setShowComparison(false);
        }
    }, [gameData?.name]);

    if (!isOpen) return null;

    const handleSearch = async (source) => {
        if (!searchQuery.trim()) return;

        setMessage(null);
        setLoading(true);
        setActiveSource(source);
        try {
            const endpoint = scrapeSource(source).search;
            // The ROM's path lets the server recognise the file by its checksum
            const body = {
                name: searchQuery,
                system_name: systemName || null,
                rom_path: gameData?.path || null
            };

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
                setMessage({ type: 'error', text: data.error || 'Search failed' });
            }
        } catch (error) {
            console.error('Search failed:', error);
            setMessage({ type: 'error', text: `Search failed: ${error.message}` });
        } finally {
            setLoading(false);
        }
    };

    const handleSelectResult = async (result) => {
        setMessage(null);
        setSelectedResult(result);
        setLoading(true);
        try {
            const endpoint = scrapeSource(currentSource).info;
            let body = { game_id: result.id, system_name: systemName || null };
            if (currentSource === 'screenscraper') {
                body = { game_id: result.id, system_id: result.systemeid, game_data: result };
            }

            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            const data = await response.json();
            if (!data.success) {
                setMessage({ type: 'error', text: `Couldn't load game details: ${data.error || 'Unknown error'}` });
            } else {
                setScraperMetadata(data.metadata);
                setMetadataSource(currentSource);
                setShowComparison(true);
                // Pre-select the matching folder for each image the game doesn't have yet
                // (the first image wins a folder). Where it already has one, the card
                // starts on Skip and shows current and new side by side.
                const defaults = {};
                const taken = new Set();
                Object.keys(data.metadata.media || {}).forEach(source => {
                    const target = DEFAULT_MEDIA_TARGET[source];
                    if (target && !taken.has(target) && !existingMediaPath(gameData, target)) {
                        defaults[source] = target;
                        taken.add(target);
                    }
                });
                setImageAssignments(defaults);
                setPreviewImage(null);
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
            setMessage({ type: 'error', text: `Couldn't load game details: ${error.message}` });
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

    // Downloads the assigned media. Returns {folder: saved path} for the files saved.
    const handleDownloadMedia = async () => {
        const media = scraperMetadata?.media || {};
        const mediaToDownload = {};

        // Each media folder holds one file per game, so the first assignment wins
        Object.entries(imageAssignments).forEach(([sourceType, targetMediaType]) => {
            if (targetMediaType && media[sourceType] && !mediaToDownload[targetMediaType]) {
                mediaToDownload[targetMediaType] = media[sourceType];
            }
        });

        const entries = Object.entries(mediaToDownload);
        if (entries.length === 0) {
            return { saved: {}, problems: [] };
        }

        // One request per file, so progress can be shown as each finishes
        const endpoint = '/api/scraper/download-media';
        const saved = {};
        const problems = [];
        setDownloadingMedia(true);
        for (let i = 0; i < entries.length; i++) {
            const [folder, url] = entries[i];
            setProgress({ done: i, total: entries.length, current: folder });
            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        system_name: systemName,
                        rom_path: gameData.path,
                        game_name: gameData.name,
                        media_types: { [folder]: url }
                    })
                });
                const result = await response.json();
                Object.assign(saved, result.saved_media || {});
                problems.push(...(result.errors || []), ...(result.error ? [`${folder}: ${result.error}`] : []));
            } catch (error) {
                problems.push(`${folder}: ${error.message}`);
            }
        }
        setProgress({ done: entries.length, total: entries.length, current: null });
        setDownloadingMedia(false);
        return { saved, problems };
    };

    const handleApplySelected = async () => {
        const mergedMetadata = { ...gameData };
        Object.entries(selectedFields).forEach(([field, isSelected]) => {
            if (isSelected && scraperMetadata[field]) {
                mergedMetadata[field] = scraperMetadata[field];
            }
        });

        // Download any media assigned to a folder, and point the form at the new files
        let problems = [];
        if (Object.values(imageAssignments).some(v => v)) {
            const result = await handleDownloadMedia();
            Object.assign(mergedMetadata, result.saved);
            problems = result.problems;
        }

        onApplyMetadata(mergedMetadata);
        setProgress(null);
        if (problems.length) {
            // Keep the popup open so the failures can be read
            setAppliedWithErrors(true);
            setMessage({ type: 'error', text: `Applied, but some media didn't download:\n${problems.join('\n')}\n\nClose this and click Save to write the rest.` });
        } else {
            onClose();
        }
    };

    const renderMediaSelection = () => {
        const media = scraperMetadata?.media || {};
        const mediaTypes = Object.keys(media);
        const mediaTypeOptions = [
            { key: '', label: 'Skip' },
            { key: 'wheel', label: 'Wheel' },
            { key: 'box2d', label: 'Box 2D' },
            { key: 'box3d', label: 'Box 3D' },
            { key: 'boxside', label: 'Spine' },
            { key: 'support', label: 'Cart / disc' },
            { key: 'screenshot', label: 'Screenshot' },
            { key: 'screenshottitle', label: 'Title screen' },
            { key: 'fanart', label: 'Fanart' },
            { key: 'posters', label: 'Posters' },
            { key: 'images', label: 'Images' },
            { key: 'mix', label: 'Mix' },
            { key: 'videos', label: 'Video' },
            { key: 'manuals', label: 'Manual' },
        ];
        
        if (mediaTypes.length === 0) {
            return (
                <div style={{backgroundColor:'var(--bg-tertiary)',padding:'15px',borderRadius:'4px',marginBottom:'15px',borderLeft:'3px solid var(--accent-orange)'}}>
                    <h4 style={{margin:'0 0 10px 0',color:'var(--accent-orange)'}}>Media Available</h4>
                    <div style={{color:'var(--text-secondary)',padding:'10px',textAlign:'center',fontSize:'13px'}}>No media available for this game</div>
                </div>
            );
        }
        
        return (
            <div style={{backgroundColor:'var(--bg-tertiary)',padding:'15px',borderRadius:'4px',marginBottom:'15px',borderLeft:'3px solid var(--accent-orange)'}}>
                <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'15px'}}>
                    <h4 style={{margin:0,color:'var(--accent-orange)'}}>Assign Media ({mediaTypes.length} available)</h4>
                </div>
                
                {previewImage && (
                    <div ref={previewRef}
                        style={{backgroundColor:'var(--bg-secondary)',padding:'15px',borderRadius:'4px',marginBottom:'15px',textAlign:'center'}}>
                        {typeof previewImage === 'string' ? (
                            <>
                                <div style={{marginBottom:'10px',color:'var(--text-secondary)'}}>Preview</div>
                                <img src={previewImage} alt="preview" style={{maxWidth:'100%',maxHeight:'300px',borderRadius:'4px'}} />
                            </>
                        ) : (
                            // Current and new side by side, same height, for comparing
                            <div style={{display:'flex',gap:'16px',justifyContent:'center',alignItems:'flex-start',flexWrap:'wrap'}}>
                                {[['Current', previewImage.current], ['New', previewImage.next]].map(([label, url]) => (
                                    <figure key={label} style={{margin:0,flex:'1 1 200px',maxWidth:'48%',minWidth:'160px'}}>
                                        <figcaption style={{marginBottom:'8px',color:'var(--text-secondary)',fontWeight:600}}>{label}</figcaption>
                                        <img src={url} alt={label} style={{maxWidth:'100%',maxHeight:'320px',borderRadius:'4px'}} />
                                    </figure>
                                ))}
                            </div>
                        )}
                        <button onClick={() => setPreviewImage(null)} style={{marginTop:'10px',padding:'6px 12px',backgroundColor:'var(--accent-pink)',color:'#fff',border:'none',borderRadius:'4px',cursor:'pointer',fontSize:'12px'}}>
                            Close Preview
                        </button>
                    </div>
                )}
                
                <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill, minmax(280px, 1fr))',gap:'10px'}}>
                    {mediaTypes.map(sourceType => (
                        <div key={sourceType} style={{backgroundColor:'var(--bg-secondary)',borderRadius:'4px',overflow:'hidden',border:'1px solid var(--border-color)'}}>
                            {/* Image preview: the new image, or current and new side by side when the game already has one */}
                            {(() => {
                                const compareFolder = imageAssignments[sourceType] || DEFAULT_MEDIA_TARGET[sourceType];
                                const current = existingMediaPath(gameData, compareFolder);
                                const showCurrent = current && !NON_IMAGE_MEDIA.has(compareFolder);
                                const pane = (label, url) => (
                                    <div style={{flex:1,minWidth:0,height:'100%',position:'relative',display:'flex',alignItems:'center',justifyContent:'center',overflow:'hidden'}}>
                                        {url && NON_IMAGE_MEDIA.has(DEFAULT_MEDIA_TARGET[sourceType] || sourceType) ? (
                                            <a href={url} target="_blank" rel="noopener noreferrer" style={{color:'var(--text-secondary)',fontSize:'13px',textAlign:'center',textDecoration:'none'}}>
                                                <div style={{fontSize:'28px'}}>{sourceType === 'manuals' ? '📄' : '🎬'}</div>
                                                {sourceType === 'manuals' ? 'Manual (PDF)' : 'Video'} · open
                                            </a>
                                        ) : url ? (
                                            <img src={url} alt={label} style={{maxWidth:'100%',maxHeight:'100%',objectFit:'contain',cursor:'zoom-in'}}
                                                onClick={() => setPreviewImage(url)} onError={e => { e.target.style.display = 'none'; }} />
                                        ) : <div style={{color:'var(--text-secondary)'}}>No image</div>}
                                        {showCurrent && (
                                            <span style={{position:'absolute',left:'4px',top:'4px',fontSize:'10px',padding:'1px 5px',borderRadius:'3px',background:'rgba(0,0,0,0.7)',color:'#fff'}}>{label}</span>
                                        )}
                                    </div>
                                );
                                return (
                                    <div style={{width:'100%',height:'120px',backgroundColor:'var(--bg-primary)',overflow:'hidden',display:'flex',gap:'2px',position:'relative'}}>
                                        {showCurrent && pane('Current', localMediaUrl(current))}
                                        {showCurrent && <div style={{width:'1px',background:'var(--border-color)'}} />}
                                        {pane('New', media[sourceType])}
                                        {media[sourceType] && !NON_IMAGE_MEDIA.has(DEFAULT_MEDIA_TARGET[sourceType] || sourceType) && (
                                            <div style={{position:'absolute',top:'4px',right:'4px',backgroundColor:'rgba(0,0,0,0.7)',padding:'4px 8px',borderRadius:'3px'}}>
                                                <button
                                                    onClick={() => setPreviewImage(showCurrent ? { current: localMediaUrl(current), next: media[sourceType] } : media[sourceType])}
                                                    style={{padding:'2px 6px',backgroundColor:'var(--accent-blue)',color:'#fff',border:'none',borderRadius:'2px',cursor:'pointer',fontSize:'11px'}}
                                                    title={showCurrent ? 'Compare full size' : 'View full size'}
                                                >
                                                    {showCurrent ? 'Compare' : 'View'}
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                );
                            })()}

                            {/* Assignment controls */}
                            <div style={{padding:'10px'}}>
                                <div style={{fontSize:'12px',color:'var(--accent-orange)',marginBottom:'6px',fontWeight:'bold',wordBreak:'break-word'}}>
                                    {mediaSourceLabel(sourceType)}
                                </div>
                                <select 
                                    value={imageAssignments[sourceType] || ''} 
                                    onChange={(e) => setImageAssignments(prev => ({...prev, [sourceType]: e.target.value}))}
                                    style={{
                                        width:'100%',
                                        padding:'6px',
                                        backgroundColor:'var(--bg-tertiary)',
                                        color:'var(--text-primary)',
                                        border:'1px solid var(--border-color)',
                                        borderRadius:'3px',
                                        fontSize:'12px',
                                        cursor:'pointer'
                                    }}
                                >
                                    {mediaTypeOptions.map(option => (
                                        <option key={option.key} value={option.key}>
                                            {option.label}
                                        </option>
                                    ))}
                                </select>
                                {(() => {
                                    const chosen = imageAssignments[sourceType];
                                    const folder = chosen || DEFAULT_MEDIA_TARGET[sourceType];
                                    if (!existingMediaPath(gameData, folder)) return null;
                                    const name = mediaSourceLabel(folder).toLowerCase();
                                    return (
                                        <div style={{fontSize:'11px',marginTop:'4px',color: chosen ? 'var(--accent-pink)' : 'var(--text-secondary)'}}>
                                            {chosen ? `Replaces the game's current ${name}` : `Keeping the current ${name}. Choose a folder to replace it.`}
                                        </div>
                                    );
                                })()}
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        );
    };

    const renderComparisonField = (field) => {
        const current = gameData?.[field] || '(empty)';
        const scraped = scraperMetadata?.[field] || '(empty)';
        
        return (
            <div key={field} style={{display:'grid',gridTemplateColumns:'40px 150px 1fr 1fr',gap:'15px',backgroundColor:'var(--bg-tertiary)',padding:'15px',borderRadius:'4px',alignItems:'start'}}>
                <div style={{display:'flex',alignItems:'center'}}>
                    <input
                        type="checkbox"
                        checked={selectedFields[field] || false}
                        onChange={() => handleFieldToggle(field)}
                    />
                </div>
                <div style={{fontWeight:'bold',color:'var(--accent-pink)',wordBreak:'break-word'}}>{field}</div>
                <div style={{backgroundColor:'var(--bg-secondary)',padding:'10px',borderRadius:'4px'}}>
                    <strong style={{fontSize:'12px',color:'var(--text-secondary)'}}>Current:</strong>
                    <div style={{color:'var(--text-primary)',marginTop:'5px',fontSize:'12px',wordBreak:'break-word'}}>{String(current).substring(0,100)}</div>
                </div>
                <div style={{backgroundColor:'var(--bg-secondary)',padding:'10px',borderRadius:'4px'}}>
                    <strong style={{fontSize:'12px',color:'var(--text-secondary)'}}>Scraped:</strong>
                    <div style={{color:'var(--text-primary)',marginTop:'5px',fontSize:'12px',wordBreak:'break-word'}}>{String(scraped).substring(0,100)}</div>
                </div>
            </div>
        );
    };

    return ReactDOM.createPortal(
        <div style={{position:'fixed',top:0,left:0,right:0,bottom:0,backgroundColor:'rgba(0,0,0,0.7)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:1000}} {...backdropClose(downloadingMedia ? null : onClose)}>
            <div style={{backgroundColor:'var(--bg-secondary)',borderRadius:'8px',border:'1px solid var(--border-color)',maxWidth:'900px',width:'90%',maxHeight:'90vh',display:'flex',flexDirection:'column'}} onClick={(e) => e.stopPropagation()}>
                <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'20px',borderBottom:'1px solid var(--border-color)'}}>
                    <h2 style={{margin:0}}>Game Metadata Search</h2>
                    <button onClick={onClose} style={{background:'none',border:'none',color:'var(--text-primary)',fontSize:'28px',cursor:'pointer'}}>×</button>
                </div>

                <div style={{flex:1,overflow:'auto',padding:'20px'}}>
                    {message && (
                        <div role="alert" style={{display:'flex',gap:12,alignItems:'flex-start',marginBottom:16,padding:'12px 14px',borderRadius:4,whiteSpace:'pre-wrap',fontSize:13,lineHeight:1.5,
                            background: message.type === 'error' ? 'rgba(255,107,157,0.12)' : 'rgba(107,93,208,0.18)',
                            border: `1px solid ${message.type === 'error' ? 'var(--accent-pink)' : 'var(--accent-blue)'}`}}>
                            <div style={{flex:1}}>{message.text}</div>
                            {!appliedWithErrors && (
                                <button onClick={() => setMessage(null)} style={{background:'none',border:'none',color:'var(--text-primary)',cursor:'pointer',fontSize:18,lineHeight:1}} aria-label="Dismiss">×</button>
                            )}
                        </div>
                    )}
                    {!showComparison ? (
                        <div>
                            <div style={{display:'flex',flexDirection:'column',gap:'12px',marginBottom:'20px'}}>
                                <input
                                    type="text"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    placeholder="Search game name..."
                                    style={{padding:'12px',backgroundColor:'var(--bg-tertiary)',border:'1px solid var(--border-color)',color:'var(--text-primary)',borderRadius:'4px',fontSize:'14px'}}
                                />
                                <div style={{display:'flex',gap:'10px',flexWrap:'wrap'}}>
                                    {SCRAPE_SOURCES.map(src => {
                                        const unavailable = sourceStatus[src.id]?.available === false;
                                        return (
                                            <button
                                                key={src.id}
                                                onClick={() => handleSearch(src.id)}
                                                disabled={loading || unavailable}
                                                style={{flex:'1 1 30%',padding:'12px 16px',border:'1px solid var(--border-color)',borderRadius:'4px',cursor: unavailable ? 'not-allowed' : 'pointer',opacity: unavailable ? 0.5 : 1,display:'flex',alignItems:'center',justifyContent:'center',gap:'8px',fontSize:'14px',fontWeight:'500',transition:'all 0.2s',backgroundColor:'var(--bg-hover)',color:'var(--text-primary)',borderColor:activeSource === src.id && !loading ? '#fff' : src.color}}
                                                title={unavailable ? sourceStatus[src.id].hint : src.title}
                                            >
                                                {src.logo && <img src={src.logo} alt="" style={{height:'20px',width:'20px'}} />}
                                                {src.label}
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>

                            {searchResults.length > 0 && (
                                <div style={{padding:'10px',backgroundColor:'var(--bg-tertiary)',borderLeft:'3px solid var(--accent-pink)',borderRadius:'4px',marginBottom:'15px',color:'var(--text-primary)',fontSize:'13px'}}>
                                    Results from: <strong>{scrapeSource(currentSource).label}</strong>
                                </div>
                            )}

                            {loading && (
                                <div style={{padding:'15px',textAlign:'center',color:'var(--accent-pink)',fontSize:'16px'}}>
                                    <div>🔍 Searching...</div>
                                </div>
                            )}

                            {!loading && searchQuery && searchResults.length === 0 && currentSource && (
                                <div style={{padding:'15px',textAlign:'center',color:'var(--accent-orange)',fontSize:'14px'}}>
                                    No results found. Try a different search term or source.
                                </div>
                            )}

                            <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill, minmax(250px, 1fr))',gap:'15px'}}>
                                {searchResults.map((result) => {
                                    const displayName = result.nom || result.name;
                                    const displaySystem = result.systemenom || result.platform_names || (result.platforms ? result.platforms.join(', ') : 'Unknown System');
                                    const displayImage = result.image || result.cover_url;
                                    const regions = (result.regions || []).map(r => r.toUpperCase()).join(' · ');
                                    
                                    return (
                                    <div
                                        key={result.id}
                                        onClick={() => handleSelectResult(result)}
                                        style={{backgroundColor:'var(--bg-tertiary)',border:selectedResult?.id === result.id ? '2px solid var(--accent-pink)' : '1px solid var(--border-color)',borderRadius:'4px',padding:'10px',cursor:'pointer',transition:'all 0.2s'}}
                                    >
                                        {displayImage && (
                                            <img src={displayImage} alt={displayName} onError={e => { e.target.style.display = 'none'; }} style={{width:'100%',height:'150px',objectFit:'cover',borderRadius:'4px',marginBottom:'10px',backgroundColor:'var(--bg-secondary)'}} />
                                        )}
                                        <div style={{color:'var(--text-primary)',fontWeight:'bold',fontSize:'14px',marginBottom:'5px'}}>
                                            {displayName}
                                            {result.year && <span style={{color:'var(--text-secondary)',fontWeight:400}}> · {result.year}</span>}
                                        </div>
                                        <div style={{color:'var(--accent-orange)',fontSize:'12px',fontWeight:'500',marginBottom:'3px'}}>Console: {displaySystem}</div>
                                        {regions && <div style={{color:'var(--text-secondary)',fontSize:'11px',marginBottom:'3px'}}>Regions: {regions}</div>}
                                        {result.hash_match && (
                                            <span title="Recognised from this ROM file's checksum" style={{display:'inline-block',marginTop:4,marginRight:4,fontSize:11,padding:'1px 6px',borderRadius:3,border:'1px solid var(--success)',color:'var(--success)'}}>ROM match</span>
                                        )}
                                        {result.is_hack && (
                                            <span style={{display:'inline-block',marginTop:4,fontSize:11,padding:'1px 6px',borderRadius:3,border:'1px solid var(--accent-pink)',color:'var(--accent-pink)'}}>Hack / mod</span>
                                        )}
                                    </div>
                                    );
                                })}
                            </div>

                            {!searchResults.length && !loading && !currentSource && (
                                <div style={{padding:'15px',textAlign:'center',color:'var(--text-secondary)',fontSize:'13px'}}>
                                    Click a search button to get started
                                </div>
                            )}
                        </div>
                    ) : (
                        <div>
                            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'20px'}}>
                                <h3 style={{margin:0}}>Compare Metadata</h3>
                                <button onClick={() => setShowComparison(false)} style={{padding:'8px 12px',backgroundColor:'var(--accent-blue)',color:'#fff',border:'none',borderRadius:'4px',cursor:'pointer'}}>
                                    ← Back to Search
                                </button>
                            </div>

                            <div style={{backgroundColor:'var(--bg-tertiary)',padding:'10px',borderRadius:'4px',marginBottom:'15px',color:'var(--text-primary)',fontSize:'13px'}}>
                                <strong>Selected ({scrapeSource(currentSource).label}):</strong> {selectedResult?.nom || selectedResult?.name}
                            </div>

                            <div style={{display:'flex',gap:'10px',marginBottom:'15px'}}>
                                <button onClick={handleApplyAll} style={{padding:'8px 12px',backgroundColor:'var(--accent-orange)',color:'#fff',border:'none',borderRadius:'4px',cursor:'pointer'}}>
                                    Select All Fields
                                </button>
                                <button onClick={() => setSelectedFields({})} style={{padding:'8px 12px',backgroundColor:'var(--accent-orange)',color:'#fff',border:'none',borderRadius:'4px',cursor:'pointer'}}>
                                    Deselect All
                                </button>
                            </div>

                            <div style={{display:'flex',flexDirection:'column',gap:'15px'}}>
                                {Object.keys(scraperMetadata)
                                    .filter(key => key !== 'media')
                                    .map(field => renderComparisonField(field))
                                }
                            </div>

                            {renderMediaSelection()}
                        </div>
                    )}
                </div>

                <div style={{display:'flex',justifyContent:'flex-end',alignItems:'center',gap:'10px',padding:'20px',borderTop:'1px solid var(--border-color)'}}>
                    {progress && (
                        <div style={{flex:1,minWidth:0}}>
                            <div style={{fontSize:12,color:'var(--text-secondary)',marginBottom:6}}>
                                {progress.current ? `Downloading ${progress.done + 1} of ${progress.total}: ${progress.current}` : `Downloaded ${progress.total} of ${progress.total}`}
                            </div>
                            <div style={{height:6,background:'var(--border-color)',borderRadius:3,overflow:'hidden'}}>
                                <div style={{height:'100%',width:`${(progress.done / progress.total) * 100}%`,background:'var(--accent-orange)',transition:'width 0.3s'}} />
                            </div>
                        </div>
                    )}
                    {appliedWithErrors ? (
                        <button onClick={onClose} style={{padding:'10px 20px',backgroundColor:'var(--accent-pink)',color:'#fff',border:'none',borderRadius:'4px',cursor:'pointer'}}>Close</button>
                    ) : (
                        <>
                            <button onClick={onClose} disabled={downloadingMedia} style={{padding:'10px 20px',backgroundColor:'var(--border-color)',color:'var(--text-primary)',border:'none',borderRadius:'4px',cursor:'pointer'}}>Cancel</button>
                            {showComparison && <button onClick={handleApplySelected} disabled={downloadingMedia} style={{padding:'10px 20px',backgroundColor:'var(--accent-pink)',color:'#fff',border:'none',borderRadius:'4px',cursor:'pointer'}}>
                                {downloadingMedia ? 'Downloading media...' : 'Apply Selected Changes'}
                            </button>}
                        </>
                    )}
                </div>
            </div>
        </div>,
        document.body
    );
};
