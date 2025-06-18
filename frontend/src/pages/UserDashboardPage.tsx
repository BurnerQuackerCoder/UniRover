import { useState, useEffect, FormEvent } from 'react';
import axiosClient from '../api/axiosClient';
import { useVoiceRecognition } from '../hooks/useVoiceRecognition'; // Import our new hook
import { speak } from '../utils/speak'; 

// Define the type for a single delivery object
interface Delivery {
  id: number;
  item: string;
  destination: string;
  notes: string | null;
  status: 'Pending' | 'Scheduled' | 'In Progress' | 'Awaiting Pickup' | 'Delivered' | 'Failed';
  created_at: string;
}

// Helper to get color styles for different statuses
const getStatusClass = (status: Delivery['status']) => {
  switch (status) {
    case 'Delivered': return 'bg-green-200 text-green-800';
    case 'In Progress': return 'bg-blue-200 text-blue-800';
    case 'Awaiting Pickup': return 'bg-yellow-200 text-yellow-800 animate-pulse';
    case 'Scheduled': return 'bg-indigo-200 text-indigo-800';
    case 'Failed': return 'bg-red-200 text-red-800';
    default: return 'bg-gray-200 text-gray-800';
  }
};

// --- NEW PARSING FUNCTION ---
const parseCommand = (transcript: string): { item: string; destination: string } | null => {
  // We can define multiple patterns to look for.
  const patterns = [
    /deliver (.*) to (.*)/i,
    /take (.*) to (.*)/i,
    /bring (.*) to (.*)/i,
    /create a delivery for (.*) to (.*)/i,
  ];

  for (const pattern of patterns) {
    const match = transcript.match(pattern);
    if (match && match.length === 3) {
      // match[1] is the first capture group (.*), match[2] is the second.
      return { item: match[1].trim(), destination: match[2].trim() };
    }
  }

  return null; // Return null if no pattern matches
};

const UserDashboardPage = () => {
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [error, setError] = useState('');
  const [formState, setFormState] = useState({ item: '', destination: '', notes: '' });

  // Use our voice recognition hook
  const { isListening, transcript, startListening, error: voiceError } = useVoiceRecognition();

  // This useEffect now provides voice feedback
  useEffect(() => {
    if (transcript) {
      const command = parseCommand(transcript);
      if (command) {
        // On success, populate the form and speak a confirmation message
        setFormState((prevState) => ({ ...prevState, item: command.item, destination: command.destination }));
        speak(`OK. Ready to deliver ${command.item} to ${command.destination}. Please press submit to confirm.`);
      } else {
        // On failure, speak an error message
        speak("Sorry, I didn't understand that. Please try saying, 'Deliver documents to Room 101'.");
      }
    }
  }, [transcript]);

  const fetchDeliveries = async () => {
    try {
      const response = await axiosClient.get('/deliveries');
      setDeliveries(response.data);
    } catch (err) {
      console.error(err);
      setError('Failed to fetch deliveries.');
    }
  };

  // Use polling to get live updates every 5 seconds
  useEffect(() => {
    fetchDeliveries(); // Fetch immediately on component mount
    const interval = setInterval(fetchDeliveries, 5000);
    return () => clearInterval(interval); // Cleanup on component unmount
  }, []);

  const handleFormChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setFormState({ ...formState, [e.target.name]: e.target.value });
  };
  
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await axiosClient.post('/deliveries', formState);
      setFormState({ item: '', destination: '', notes: '' }); // Reset form
      fetchDeliveries(); // Refresh list immediately
    } catch (err) {
      setError('Failed to create delivery request.');
      console.error(err);
    }
  };

  const handleConfirmPickup = async (deliveryId: number) => {
    try {
      await axiosClient.post(`/deliveries/${deliveryId}/confirm_pickup`);
      fetchDeliveries(); // Refresh list immediately
    } catch (err) {
      alert('Failed to confirm pickup.');
      console.error(err);
    }
  };

  return (
    <div className="space-y-8">
      {/* Create Delivery Form */}
      <div className="p-6 bg-white rounded-lg shadow-md">
        {/* Form Title and new Voice Command Button */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold">Create a New Delivery Request</h2>
          <button
            type="button"
            onClick={startListening} // Connect the button to our hook's function
            className={`p-2 rounded-full hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
              isListening ? 'animate-pulse bg-red-200' : '' // Add a visual indicator when listening
            }`}
            title="Use Voice Command"
          >
            {/* SVG Icon for a microphone */}
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-6 w-6 text-gray-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
              />
            </svg>
          </button>
        </div>
        {voiceError && <p className="text-sm text-red-500 mb-2">{voiceError}</p>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium">Item</label>
              <input name="item" type="text" value={formState.item} onChange={handleFormChange} required className="w-full px-3 py-2 mt-1 border rounded-md" placeholder="e.g., Documents" />
            </div>
            <div>
              <label className="block text-sm font-medium">Destination</label>
              <input name="destination" type="text" value={formState.destination} onChange={handleFormChange} required className="w-full px-3 py-2 mt-1 border rounded-md" placeholder="e.g., Room 101" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium">Notes (Optional)</label>
            <textarea name="notes" value={formState.notes} onChange={handleFormChange} className="w-full px-3 py-2 mt-1 border rounded-md" />
          </div>
          <button type="submit" className="w-full px-4 py-2 font-bold text-white bg-blue-600 rounded-md hover:bg-blue-700">Submit Request</button>
        </form>
      </div>

      {/* Delivery List */}
      <div className="p-6 bg-white rounded-lg shadow-md">
        <h2 className="text-2xl font-bold mb-4">My Delivery History</h2>
        {error ? (
          <p className="text-red-500">{error}</p>
        ) : deliveries.length === 0 ? (
          <p>You have no delivery requests.</p>
        ) : (
          <ul className="space-y-4">
            {deliveries.map((delivery) => (
              <li key={delivery.id} className="p-4 border rounded-md flex justify-between items-center">
                <div>
                  <p className="font-bold">{delivery.item} to {delivery.destination}</p>
                  <p className="text-sm text-gray-500">Requested on: {new Date(delivery.created_at).toLocaleString()}</p>
                </div>
                <div className="flex items-center space-x-4">
                  <span className={`px-3 py-1 text-sm font-semibold rounded-full ${getStatusClass(delivery.status)}`}>
                    {delivery.status}
                  </span>
                  {delivery.status === 'Awaiting Pickup' && (
                    <button onClick={() => handleConfirmPickup(delivery.id)} className="px-4 py-2 font-bold text-white bg-green-600 rounded-md hover:bg-green-700">
                      Confirm Pickup
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

export default UserDashboardPage;