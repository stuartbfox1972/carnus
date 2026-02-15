import React, { useState, useEffect } from 'react';
import { Authenticator } from '@aws-amplify/ui-react';
import { fetchAuthSession } from 'aws-amplify/auth';
import TagCloud from './components/TagCloud';
import GalleryGrid from './components/GalleryGrid';
import ImageModal from './components/ImageModal';
import ProfileView from './components/ProfileView';
import '@aws-amplify/ui-react/styles.css';

const globalStyles = `
  .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(15, 23, 42, 0.9); display: flex; align-items: center; justify-content: center; z-index: 1000; }
  .ai-pill { cursor: pointer; transition: all 0.2s; }
  .ai-pill:hover { transform: scale(1.05); background: #dbeafe !important; }
`;

function Dashboard({ signOut, user }) {
  const [tags, setTags] = useState([]);
  const [profile, setProfile] = useState(null);
  const [images, setImages] = useState([]);
  const [selectedTag, setSelectedTag] = useState(null);
  const [selectedImage, setSelectedImage] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [nextKey, setNextKey] = useState(null);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState('gallery');

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

  const fetchProfile = async () => {
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      const response = await fetch('/profile', { headers: { 'Authorization': token } });
      if (response.ok) {
        const data = await response.json();
        setProfile(data);
      }
    } catch (e) { console.error("Profile Fetch Error:", e); }
  };

  const handleAvatarUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const lastUpdate = profile?.AvatarUpdatedAt || 0;
    const secondsSinceUpdate = Date.now() / 1000 - lastUpdate;
    if (secondsSinceUpdate < 86400) {
      alert("You can only change your avatar once every 24 hours.");
      return;
    }

    if (file.size > 20 * 1024) {
      alert("Avatar must be under 20KB.");
      return;
    }

    const reader = new FileReader();
    reader.onloadend = async () => {
      const base64String = reader.result.split(',')[1];
      await saveProfile(null, { AvatarBlob: base64String });
    };
    reader.readAsDataURL(file);
  };

  const saveProfile = async (e, extraUpdates = {}) => {
    if (e) e.preventDefault();
    const formData = e ? new FormData(e.target) : new FormData();
    const updates = {
      FirstName: formData.get('FirstName') || profile?.FirstName || '',
      LastName: formData.get('LastName') || profile?.LastName || '',
      ...extraUpdates
    };

    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      const response = await fetch('/profile', {
        method: 'POST',
        headers: {
          'Authorization': token,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(updates)
      });
      if (response.ok) {
        await fetchProfile();
        if (e) setView('gallery');
      } else if (response.status === 418) {
        alert("I'm a teapot: Cooldown still active.");
      }
    } catch (e) { console.error("Save Profile Error:", e); }
  };

  const handleTagClick = async (tagValue, isLoadMore = false) => {
    if (!tagValue) return;
    setSelectedTag(tagValue);
    setSelectedImage(null);
    if (!isLoadMore) { setImages([]); setNextKey(null); setLoading(true); }

    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      let url = `/tags/${encodeURIComponent(tagValue)}?limit=50`;
      if (isLoadMore && nextKey) url += `&next_token=${encodeURIComponent(nextKey)}`;
      const response = await fetch(url, { headers: { 'Authorization': token } });
      const data = await response.json();
      if (data?.items) {
        setImages(prev => isLoadMore ? [...prev, ...data.items] : data.items);
        setNextKey(data.next_token || null);
      }
    } catch (err) { console.error("Gallery Fetch Error:", err); } finally { setLoading(false); }
  };

  const handleImageClick = async (galleryItem) => {
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      const response = await fetch(`/image/${galleryItem.ImageId}`, {
        headers: { 'Authorization': token }
      });
      const fullImageData = await response.json();
      setSelectedImage(fullImageData);
    } catch (err) { setSelectedImage(galleryItem); }
  };

  useEffect(() => { if (user) { fetchTags(); fetchProfile(); } }, [user]);

  return (
    <div style={{ minHeight: '100vh', background: '#f8f9fa' }}>
      <style>{globalStyles}</style>

      <header style={{ background: '#232f3e', color: 'white', padding: '0.75rem 2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong onClick={() => { setView('gallery'); setSelectedTag(null); }} style={{ cursor: 'pointer' }}>CARNUS CONSOLE</strong>
        <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
            <span style={{ fontSize: '10px', color: '#a0aec0', fontWeight: 'bold', letterSpacing: '0.02em' }}>
              {((profile?.StorageBytesUsed || 0) / 1024 / 1024).toFixed(1)} MB / {((profile?.StorageQuota || 53687091200) / 1024 / 1024 / 1024).toFixed(1)} GB
            </span>
            <div style={{ width: '80px', height: '4px', background: '#37475a', borderRadius: '2px', overflow: 'hidden' }}>
              <div style={{ 
                width: `${Math.min(100, ((profile?.StorageUsed || 0) / (profile?.StorageQuota || 53687091200)) * 100)}%`, 
                height: '100%', 
                background: '#63b3ed',
                transition: 'width 0.8s ease-in-out'
              }} />
            </div>
          </div>
          <div onClick={() => setView('profile')} style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer', padding: '6px 10px', borderRadius: '4px', background: view === 'profile' ? '#37475a' : 'transparent', border: view === 'profile' ? '1px solid #4a5568' : '1px solid transparent' }}>
            <div style={{ width: '32px', height: '32px', borderRadius: '4px', background: '#a0aec0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold', color: 'white', fontSize: '14px', overflow: 'hidden' }}>
              {profile?.AvatarUrl ? (
                <img src={profile.AvatarUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                (profile?.FirstName || profile?.DisplayName || profile?.Email || 'U').charAt(0).toUpperCase()
              )}
            </div>
            <span style={{ fontSize: '14px' }}>
              {profile?.FirstName || profile?.Email || (loading ? 'Loading...' : 'User')}
            </span>
          </div>
          <button onClick={signOut} style={{ padding: '5px 15px', borderRadius: '4px', cursor: 'pointer' }}>Sign Out</button>
        </div>
      </header>

      <main style={{ padding: '40px', maxWidth: '1200px', margin: '0 auto' }}>
        {view === 'profile' ? (
          <ProfileView
            profile={profile}
            onSave={saveProfile}
            onAvatarUpload={handleAvatarUpload}
            onCancel={() => setView('gallery')}
          />
        ) : (
          <>
            {selectedImage && <ImageModal image={selectedImage} onClose={() => setSelectedImage(null)} onTagClick={handleTagClick} />}
            {!selectedTag ? (
              <TagCloud tags={tags} searchQuery={searchQuery} onSearchChange={setSearchQuery} onTagClick={handleTagClick} />
            ) : (
              <GalleryGrid images={images} selectedTag={selectedTag} onImageClick={handleImageClick} onBack={() => { setSelectedTag(null); setImages([]); }} nextKey={nextKey} onLoadMore={() => handleTagClick(selectedTag, true)} />
            )}
          </>
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
