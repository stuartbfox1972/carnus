import React, { useState, useEffect } from 'react';
import { Authenticator } from '@aws-amplify/ui-react';
import { fetchAuthSession } from 'aws-amplify/auth';
import TagCloud from './components/TagCloud';
import GalleryGrid from './components/GalleryGrid';
import ImageModal from './components/ImageModal';
import '@aws-amplify/ui-react/styles.css';

const globalStyles = `
  .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(15, 23, 42, 0.9); display: flex; align-items: center; justify-content: center; z-index: 1000; }
  .ai-pill { cursor: pointer; transition: all 0.2s; }
  .ai-pill:hover { transform: scale(1.05); background: #dbeafe !important; }
`;

function Dashboard({ signOut, user }) {
  const [tags, setTags] = useState([]);
  const [images, setImages] = useState([]);
  const [selectedTag, setSelectedTag] = useState(null);
  const [selectedImage, setSelectedImage] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [nextKey, setNextKey] = useState(null);
  const [loading, setLoading] = useState(false);

  // Fetch initial TagCloud
  const fetchTags = async () => {
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      const response = await fetch('/tags', { headers: { 'Authorization': token } });
      const data = await response.json();
      if (Array.isArray(data)) {
        setTags(data.map(item => ({
          LabelName: item.Text,
          Count: item.Count,
          SK: `TAG#${item.Text}`
        })));
      }
    } catch (e) { console.error("Tag Fetch Error:", e); }
  };

  // The pivot function used by TagCloud AND ImageModal pills
  const handleTagClick = async (tagValue, isLoadMore = false) => {
    if (!tagValue) return;
    
    // Normalize tag for DynamoDB GSI (TAG#Name)
    const dbTag = tagValue.startsWith('TAG#') ? tagValue : `TAG#${tagValue}`;
    setSelectedTag(dbTag);
    setSelectedImage(null); // Close modal if open

    if (!isLoadMore) {
      setImages([]);
      setNextKey(null);
      setLoading(true);
    }

    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      let url = `/tags/${encodeURIComponent(dbTag)}?limit=50`;
      if (isLoadMore && nextKey) url += `&next_token=${encodeURIComponent(nextKey)}`;

      const response = await fetch(url, { headers: { 'Authorization': token } });
      const data = await response.json();
      if (data?.items) {
        setImages(prev => isLoadMore ? [...prev, ...data.items] : data.items);
        setNextKey(data.next_token || null);
      }
    } catch (err) {
      console.error("Gallery Fetch Error:", err);
    } finally {
      setLoading(false);
    }
  };

  // Fetch the full image data (with Labels) when thumbnail is clicked
  const handleImageClick = async (galleryItem) => {
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      const response = await fetch(`/image/${galleryItem.ImageId}`, {
        headers: { 'Authorization': token }
      });
      
      if (!response.ok) throw new Error("Failed to fetch full image details");
      const fullImageData = await response.json();
      
      setSelectedImage(fullImageData);
    } catch (err) {
      console.error("Detail Fetch Error:", err);
      setSelectedImage(galleryItem); // Fallback to shallow data
    }
  };

  useEffect(() => { if (user) fetchTags(); }, [user]);

  return (
    <div style={{ minHeight: '100vh', background: '#f8f9fa' }}>
      <style>{globalStyles}</style>

      <header style={{ background: '#232f3e', color: 'white', padding: '1rem 2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong onClick={() => window.location.reload()} style={{ cursor: 'pointer' }}>CARNUS CONSOLE</strong>
        <div style={{ display: 'flex', gap: '15px', alignItems: 'center' }}>
          <span>{user?.username}</span>
          <button onClick={signOut} style={{ padding: '5px 15px', borderRadius: '4px', cursor: 'pointer' }}>Sign Out</button>
        </div>
      </header>

      <main style={{ padding: '40px', maxWidth: '1200px', margin: '0 auto' }}>
        
        {/* IMPORTANT: Passing onTagClick here so pills can trigger handleTagClick */}
        {selectedImage && (
          <ImageModal 
            image={selectedImage} 
            onClose={() => setSelectedImage(null)} 
            onTagClick={handleTagClick} 
          />
        )}

        {!selectedTag ? (
          <TagCloud 
            tags={tags} 
            searchQuery={searchQuery} 
            onSearchChange={setSearchQuery} 
            onTagClick={handleTagClick} 
          />
        ) : (
          <GalleryGrid
            images={images}
            selectedTag={selectedTag}
            onImageClick={handleImageClick}
            onBack={() => { setSelectedTag(null); setImages([]); }}
            nextKey={nextKey}
            onLoadMore={() => handleTagClick(selectedTag, true)}
          />
        )}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Authenticator.Provider>
      <Authenticator>
        {({ signOut, user }) => <Dashboard signOut={signOut} user={user} />}
      </Authenticator>
    </Authenticator.Provider>
  );
}
