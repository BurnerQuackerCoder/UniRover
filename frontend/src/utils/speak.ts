/**
 * Uses the browser's SpeechSynthesis API to speak a given text string aloud.
 * @param text The string of text to be spoken.
 */
export const speak = (text: string): void => {
  // Check if the browser supports the SpeechSynthesis API
  if (!window.speechSynthesis) {
    console.warn("Speech synthesis is not supported in this browser.");
    return;
  }

  // Cancel any speech that might be ongoing
  window.speechSynthesis.cancel();

  // Create a new utterance with the provided text
  const utterance = new SpeechSynthesisUtterance(text);

  // Optional: Configure the voice, rate, pitch, etc.
  utterance.lang = 'en-US'; // Set language
  utterance.rate = 1.0;     // Speed of speech (0.1 to 10)
  utterance.pitch = 1.0;    // Pitch of speech (0 to 2)

  // Speak the utterance
  window.speechSynthesis.speak(utterance);
};