import { ChatArea } from '../components/Chat/ChatArea';
import { InputArea } from '../components/Chat/InputArea';

export function ChatPage() {
  return (
    <div className="flex flex-col h-full">
      <ChatArea />
      <InputArea />
    </div>
  );
}
