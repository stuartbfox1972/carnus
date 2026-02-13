import React, { useState } from 'react';

const ImageModal = ({ image, onClose, onTagClick }) => {
  const [hoveredFace, setHoveredFace] = useState(null);

  if (!image) return null;

  const imageUrl = image.DetailUrl || image.ThumbnailUrl;
  const labels = image.Labels || [];
  const faces = image.Faces || [];

  // Helper to match DynamoDB TAG# logic: "HAPPY" -> "Happy", "EyesOpen" -> "Eyes Open"
  const normalizeTag = (str) => {
    if (!str) return '';
    // First, split camelCase (EyesOpen -> Eyes Open)
    const spaced = str.replace(/([A-Z])/g, ' $1').trim();
    // Then capitalize first letter of each word
    return spaced.split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  };

  const renderDynamicPill = (key, value) => {
    const blacklist = ['BoundingBox', 'Confidence', 'Landmarks', 'Emotions'];
    if (blacklist.includes(key) || !value) return null;

    let displayLabel = key;
    let searchTag = key;

    if (key === 'AgeRange') {
      displayLabel = `Age ${value.Low}-${value.High}`;
      searchTag = displayLabel;
    } else if (typeof value === 'boolean') {
      if (value === false) return null;
      searchTag = normalizeTag(key); // "EyesOpen" -> "Eyes Open"
      displayLabel = searchTag.toUpperCase();
    } else if (typeof value === 'string') {
      searchTag = normalizeTag(value); // "FEMALE" -> "Female"
      displayLabel = value.toUpperCase();
    }

    return (
      <button
        key={key}
        onClick={() => { onTagClick(searchTag); onClose(); }}
        style={styles.facePill}
      >
        {displayLabel}
      </button>
    );
  };

  return (
    <div className="modal-overlay" onClick={onClose} style={styles.overlay}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={styles.content}>
        
        {/* IMAGE & FACE BOXES */}
        <div 
          style={{ position: 'relative', width: '100%', marginBottom: '20px' }}
          onMouseLeave={() => setHoveredFace(null)} 
        >
          <img src={imageUrl} alt="Detail" style={styles.mainImage} />
          
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={styles.svgOverlay}>
            {faces.map((face, i) => (
              <rect
                key={i}
                x={face.BoundingBox.Left * 100}
                y={face.BoundingBox.Top * 100}
                width={face.BoundingBox.Width * 100}
                height={face.BoundingBox.Height * 100}
                fill="transparent"
                stroke="#ef4444"
                strokeWidth="0.8"
                style={{ cursor: 'pointer', pointerEvents: 'auto' }}
                onMouseEnter={() => setHoveredFace(face)}
              />
            ))}
          </svg>

          {/* ATTRIBUTE POPUP */}
          {hoveredFace && (
            <div style={{
              ...styles.popup,
              left: `${(hoveredFace.BoundingBox.Left + hoveredFace.BoundingBox.Width) * 100}%`,
              top: `${hoveredFace.BoundingBox.Top * 100}%`,
            }}>
              <div style={styles.popupHeader}>FACE DATA</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                
                {/* 1. Attributes (Gender, Age, Booleans) */}
                {Object.keys(hoveredFace).map(key => renderDynamicPill(key, hoveredFace[key]))}

                {/* 2. Emotions (Normalized for search) */}
                {hoveredFace.Emotions?.map((emo) => (
                  <button 
                    key={emo} 
                    onClick={() => { onTagClick(normalizeTag(emo)); onClose(); }} 
                    style={styles.emotionPill}
                  >
                    {emo.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* BLUE PILL BAR (Standard AI Labels) */}
        <div style={styles.labelBar}>
          {labels.map((tag, i) => (
            <button 
              key={i} 
              onClick={() => { onTagClick(normalizeTag(tag)); onClose(); }} 
              style={styles.bluePill}
            >
              {tag}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

const styles = {
  overlay: {
    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(15, 23, 42, 0.95)', display: 'flex', 
    alignItems: 'center', justifyContent: 'center', zIndex: 1000
  },
  content: {
    background: 'white', padding: '24px', borderRadius: '16px',
    maxWidth: '900px', width: '95%', maxHeight: '95vh', overflowY: 'auto'
  },
  mainImage: { width: '100%', borderRadius: '12px', display: 'block' },
  svgOverlay: { position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' },
  popup: {
    position: 'absolute', background: 'white', border: '1px solid #ef4444', 
    borderRadius: '8px', padding: '12px', zIndex: 10, boxShadow: '0 10px 15px -3px rgba(0,0,0,0.2)',
    minWidth: '160px', marginLeft: '10px'
  },
  popupHeader: { fontWeight: 'bold', marginBottom: '8px', fontSize: '10px', color: '#94a3b8', letterSpacing: '0.05em' },
  facePill: {
    background: '#f8fafc', color: '#475569', border: '1px solid #e2e8f0', 
    padding: '5px 10px', borderRadius: '4px', fontSize: '11px', fontWeight: '800', 
    cursor: 'pointer', textAlign: 'left'
  },
  emotionPill: {
    background: '#fee2e2', color: '#b91c1c', border: 'none', 
    padding: '5px 10px', borderRadius: '4px', fontSize: '11px', 
    fontWeight: '800', cursor: 'pointer', textAlign: 'left'
  },
  labelBar: { display: 'flex', gap: '8px', flexWrap: 'wrap', borderTop: '1px solid #f1f5f9', paddingTop: '20px' },
  bluePill: {
    background: '#eff6ff', color: '#1d4ed8', border: '1px solid #dbeafe', 
    padding: '6px 14px', borderRadius: '20px', fontSize: '13px', 
    fontWeight: '600', cursor: 'pointer'
  }
};

export default ImageModal;
