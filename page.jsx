//react code
'use client'; // This must be at the very top for a single-file interactive app

import { useState, useEffect } from 'react';

export default function SingleFileApp() {
  const [users, setUsers] = useState([]);      // Stores all data from the internet
  const [searchTerm, setSearchTerm] = useState(''); // Stores what you type

  // 1. Fetch data when the page first opens
  useEffect(() => {
    fetch('https://typicode.com')
      .then((res) => res.json())
      .then((data) => setUsers(data));
  }, []);

  // 2. Logic: Filter the list as you type
  const filteredUsers = users.filter((user) =>
    user.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="max-w-md mx-auto p-10 font-sans">
      <h1 className="text-2xl font-bold mb-5 text-blue-600">User Search</h1>

      {/* SEARCH BAR */}
      <input
        type="text"
        placeholder="Search by name..."
        className="w-full p-3 border-2 border-gray-200 rounded-lg focus:border-blue-400 outline-none mb-6"
        onChange={(e) => setSearchTerm(e.target.value)}
      />

      {/* RESULTS LIST */}
      <div className="space-y-3">
        {filteredUsers.map((user) => (
          <div key={user.id} className="p-4 bg-gray-50 rounded shadow-sm border-l-4 border-blue-500">
            <p className="font-bold text-gray-800">{user.name}</p>
            <p className="text-sm text-gray-500">{user.email}</p>
          </div>
        ))}
        
        {/* If nothing matches */}
        {filteredUsers.length === 0 && users.length > 0 && (
          <p className="text-center text-gray-400 mt-4">No names match your search.</p>
        )}
      </div>
    </div>
  );
}
