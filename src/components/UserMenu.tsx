import { useState } from 'react';
import { useAuth } from '@/services/auth';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Settings, CheckCircle2, XCircle, AlertCircle, ExternalLink, LogOut, LogIn } from 'lucide-react';
import { toast } from 'sonner';

const UserMenu = () => {
  const { user, login, logout, sessionState, isLoading, supabaseUser, signOut, isAuthenticated } = useAuth();
  const [open, setOpen] = useState(false);

  const handleOAuthLogin = async () => {
    await login();
    setOpen(false);
  };

  const handleSignOut = async () => {
    await logout();
    await signOut();
    toast.success('Signed out');
    setOpen(false);
  };

  if (isLoading) return null;

  const navigate = useNavigate();

  if (!isAuthenticated) {
    return (
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" className="h-8 px-2 text-xs" onClick={() => navigate('/login')}>
          <LogIn className="mr-1.5 h-3.5 w-3.5" />
          Sign In
        </Button>
      </div>
    );
  }

  const connected = sessionState === 'connected' && !!user;
  return (
    <div className="flex items-center gap-2">
      {connected && (
        <span className="text-xs font-mono text-foreground" data-testid="auth-connected">
          {user.accountName}
        </span>
      )}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="ghost" size="icon" className="h-8 w-8 gear-spin" data-testid="settings-trigger">
            <Settings className="h-4 w-4" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-72 space-y-3 border-primary/30 animate-scale-fade-in">
          {supabaseUser && (
            <div className="text-xs text-muted-foreground truncate">
              {supabaseUser.email}
            </div>
          )}

          <div className="flex items-center gap-2 text-xs">
            {sessionState === 'connected' && user ? (
              <><CheckCircle2 className="h-3.5 w-3.5 text-primary" /><span className="text-muted-foreground">Connected as <strong className="text-foreground">{user.accountName}</strong></span></>
            ) : sessionState === 'session_expired' ? (
              <><AlertCircle className="h-3.5 w-3.5 text-warning" /><span className="text-muted-foreground">Session expired</span></>
            ) : (
              <><XCircle className="h-3.5 w-3.5 text-destructive" /><span className="text-muted-foreground">Not connected</span></>
            )}
          </div>

          {!connected && (
            <Button size="sm" className="w-full gap-2 text-xs h-8 btn-game" onClick={handleOAuthLogin}>
              <ExternalLink className="h-3.5 w-3.5" />
              Connect Path of Exile
            </Button>
          )}

          <Button size="sm" variant="ghost" className="w-full gap-2 text-xs h-7 text-muted-foreground hover:text-foreground" onClick={handleSignOut}>
            <LogOut className="h-3 w-3" /> Sign Out
          </Button>
        </PopoverContent>
      </Popover>
    </div>
  );
};

export default UserMenu;
