/** @jest-environment jsdom */
import React from 'react';
import {act,render,screen,waitFor} from '@testing-library/react';
import {PortfolioProvider,usePortfolio} from '../../contexts/PortfolioContext';
let mockUser:any={id:'A'};
jest.mock('../../contexts/AuthContext',()=>({useAuth:()=>({user:mockUser})}));
function Probe(){const {snapshot}=usePortfolio();return <span>{snapshot?.positions[0]?.symbol || 'empty'}</span>}
it('never shows another account snapshot or lets an older request overwrite the new account',async()=>{
 let resolveA!:(value:any)=>void,resolveB!:(value:any)=>void;
 const a=new Promise(resolve=>{resolveA=resolve}),b=new Promise(resolve=>{resolveB=resolve});
 global.fetch=jest.fn().mockImplementationOnce(()=>a).mockImplementationOnce(()=>b);
 const {rerender}=render(<PortfolioProvider><Probe/></PortfolioProvider>);
 await waitFor(()=>expect(global.fetch).toHaveBeenCalledTimes(1));
 mockUser={id:'B'};rerender(<PortfolioProvider><Probe/></PortfolioProvider>);
 await waitFor(()=>expect(global.fetch).toHaveBeenCalledTimes(2));
 await act(async()=>{resolveB({ok:true,json:async()=>({positions:[{symbol:'B-HOLDING'}]})})});
 expect(screen.getByText('B-HOLDING')).toBeTruthy();
 await act(async()=>{resolveA({ok:true,json:async()=>({positions:[{symbol:'A-PRIVATE'}]})})});
 expect(screen.queryByText('A-PRIVATE')).toBeNull();expect(screen.getByText('B-HOLDING')).toBeTruthy();
 mockUser=null;rerender(<PortfolioProvider><Probe/></PortfolioProvider>);expect(screen.getByText('empty')).toBeTruthy();
});
