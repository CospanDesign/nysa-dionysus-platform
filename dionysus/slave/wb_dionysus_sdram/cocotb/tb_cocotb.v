`timescale 1ns/1ps
//`include "project_defines.v"

module tb_cocotb (

//Virtual Host Interface Signals
input               clk,
input               rst,

input       [31:0]  test_id,
output              device_interrupt,

output      [1:0]   ingress_rdy,
input       [1:0]   ingress_act,
input               ingress_stb,
input       [31:0]  ingress_data,
output      [23:0]  ingress_size,

output              egress_rdy,
input               egress_act,
input               egress_stb,
output      [31:0]  egress_data,
output      [23:0]  egress_size

);

reg                 r_rst;
reg         [1:0]   r_ingress_act;
reg                 r_ingress_stb;
reg         [31:0]  r_ingress_data;
reg                 r_egress_clk;
reg                 r_egress_act;
reg                 r_egress_stb;


//There is a bug in COCOTB when stiumlating a signal, sometimes it can be corrupted if not registered
always @ (*) r_rst          = rst;
always @ (*) r_ingress_act  = ingress_act;
always @ (*) r_ingress_stb  = ingress_stb;
always @ (*) r_ingress_data = ingress_data;
always @ (*) r_egress_act   = egress_act;
always @ (*) r_egress_stb   = egress_stb;

//Parameters
//Registers/Wires

//wishbone signals
wire              w_wbp_we;
wire              w_wbp_cyc;
wire              w_wbp_stb;
wire [3:0]        w_wbp_sel;
wire [31:0]       w_wbp_adr;
wire [31:0]       w_wbp_dat_o;
wire [31:0]       w_wbp_dat_i;
wire              w_wbp_ack;
wire              w_wbp_int;

//Wishbone Slave 0 (SDB) signals
wire              w_wbs0_we;
wire              w_wbs0_cyc;
wire  [31:0]      w_wbs0_dat_o;
wire              w_wbs0_stb;
wire  [3:0]       w_wbs0_sel;
wire              w_wbs0_ack;
wire  [31:0]      w_wbs0_dat_i;
wire  [31:0]      w_wbs0_adr;
wire              w_wbs0_int;

//mem slave 0
wire              w_sm0_i_wbs_we;
wire              w_sm0_i_wbs_cyc;
wire  [31:0]      w_sm0_i_wbs_dat;
wire  [31:0]      w_sm0_o_wbs_dat;
wire  [31:0]      w_sm0_i_wbs_adr;
wire              w_sm0_i_wbs_stb;
wire  [3:0]       w_sm0_i_wbs_sel;
wire              w_sm0_o_wbs_ack;
wire              w_sm0_o_wbs_int;

//wishbone slave 1 (Unit Under Test) signals
wire              w_wbs1_we;
wire              w_wbs1_cyc;
wire              w_wbs1_stb;
wire  [3:0]       w_wbs1_sel;
wire              w_wbs1_ack;
wire  [31:0]      w_wbs1_dat_i;
wire  [31:0]      w_wbs1_dat_o;
wire  [31:0]      w_wbs1_adr;
wire              w_wbs1_int;

//Memory Interface
wire              w_mem_we_o;
wire              w_mem_cyc_o;
wire              w_mem_stb_o;
wire  [3:0]       w_mem_sel_o;
wire  [31:0]      w_mem_adr_o;
wire  [31:0]      w_mem_dat_i;
wire  [31:0]      w_mem_dat_o;
wire              w_mem_ack_i;
wire              w_mem_int_i;

wire              w_arb0_i_wbs_stb;
wire              w_arb0_i_wbs_cyc;
wire              w_arb0_i_wbs_we;
wire  [3:0]       w_arb0_i_wbs_sel;
wire  [31:0]      w_arb0_i_wbs_dat;
wire  [31:0]      w_arb0_o_wbs_dat;
wire  [31:0]      w_arb0_i_wbs_adr;
wire              w_arb0_o_wbs_ack;
wire              w_arb0_o_wbs_int;


wire              mem_o_we;
wire              mem_o_stb;
wire              mem_o_cyc;
wire  [3:0]       mem_o_sel;
wire  [31:0]      mem_o_adr;
wire  [31:0]      mem_o_dat;
wire  [31:0]      mem_i_dat;
wire              mem_i_ack;
wire              mem_i_int;


wire              sdram_clk;
wire              sdram_cke;
wire              sdram_cs_n;
wire              sdram_ras;
wire              sdram_cas;
wire              sdram_we;
wire      [11:0]  sdram_addr;
wire      [1:0]   sdram_bank;
wire      [15:0]  sdram_data;
wire      [1:0]   sdram_data_mask;
wire              sdram_ready;
reg       [15:0]  sdram_in_data;





//Submodules
wishbone_master #(
//  .INGRESS_FIFO_DEPTH    (9                ),
//  .EGRESS_FIFO_DEPTH     (9                ),
//  .ENABLE_WRITE_RESP     (0                ),
//  .ENABLE_NACK           (0                ),
//  .DEFAULT_TIMEOUT       (`CLOCK_RATE      )
) wm (

  .clk                   (clk              ),
  .rst                   (r_rst            ),


  //indicate to the input that we are ready
  .i_ingress_clk         (clk              ),
  .o_ingress_rdy         (ingress_rdy      ),
  .i_ingress_act         (r_ingress_act    ),
  .i_ingress_stb         (r_ingress_stb    ),
  .i_ingress_data        (r_ingress_data   ),
  .o_ingress_size        (ingress_size     ),

  .i_egress_clk          (clk              ),
  .o_egress_rdy          (egress_rdy       ),
  .i_egress_act          (r_egress_act     ),
  .i_egress_stb          (r_egress_stb     ),
  .o_egress_data         (egress_data      ),
  .o_egress_size         (egress_size      ),

  //General Control
  .o_sync_rst            (w_sync_rst       ),

  .o_per_we              (w_wbp_we         ),
  .o_per_adr             (w_wbp_adr        ),
  .o_per_dat             (w_wbp_dat_i      ),
  .i_per_dat             (w_wbp_dat_o      ),
  .o_per_stb             (w_wbp_stb        ),
  .o_per_cyc             (w_wbp_cyc        ),
  .o_per_msk             (w_wbp_msk        ),
  .o_per_sel             (w_wbp_sel        ),
  .i_per_ack             (w_wbp_ack        ),
  .i_per_int             (w_wbp_int        ),

  //memory interconnect signals
  .o_mem_we              (w_mem_we_o       ),
  .o_mem_adr             (w_mem_adr_o      ),
  .o_mem_dat             (w_mem_dat_o      ),
  .i_mem_dat             (w_mem_dat_i      ),
  .o_mem_stb             (w_mem_stb_o      ),
  .o_mem_cyc             (w_mem_cyc_o      ),
  .o_mem_sel             (w_mem_sel_o      ),
  .i_mem_ack             (w_mem_ack_i      ),
  .i_mem_int             (w_mem_int_i      )


);

//slave 1
dionysus_sdram_tester s1 (

  .clk                  (clk                  ),
  .rst                  (r_rst                ),

  .i_wbs_we             (w_wbs1_we            ),
  .i_wbs_sel            (4'b1111              ),
  .i_wbs_cyc            (w_wbs1_cyc           ),
  .i_wbs_dat            (w_wbs1_dat_i         ),
  .i_wbs_stb            (w_wbs1_stb           ),
  .o_wbs_ack            (w_wbs1_ack           ),
  .o_wbs_dat            (w_wbs1_dat_o         ),
  .i_wbs_adr            (w_wbs1_adr           ),
  .o_wbs_int            (w_wbs1_int           )
);

wishbone_interconnect wi (
  .clk        (clk                  ),
  .rst        (r_rst                ),

  .i_m_we     (w_wbp_we             ),
  .i_m_cyc    (w_wbp_cyc            ),
  .i_m_stb    (w_wbp_stb            ),
  .o_m_ack    (w_wbp_ack            ),
  .i_m_dat    (w_wbp_dat_i          ),
  .o_m_dat    (w_wbp_dat_o          ),
  .i_m_adr    (w_wbp_adr            ),
  .o_m_int    (w_wbp_int            ),

  .o_s0_we    (w_wbs0_we            ),
  .o_s0_cyc   (w_wbs0_cyc           ),
  .o_s0_stb   (w_wbs0_stb           ),
  .i_s0_ack   (w_wbs0_ack           ),
  .o_s0_dat   (w_wbs0_dat_i         ),
  .i_s0_dat   (w_wbs0_dat_o         ),
  .o_s0_adr   (w_wbs0_adr           ),
  .i_s0_int   (w_wbs0_int           ),

  .o_s1_we    (w_wbs1_we            ),
  .o_s1_cyc   (w_wbs1_cyc           ),
  .o_s1_stb   (w_wbs1_stb           ),
  .i_s1_ack   (w_wbs1_ack           ),
  .o_s1_dat   (w_wbs1_dat_i         ),
  .i_s1_dat   (w_wbs1_dat_o         ),
  .o_s1_adr   (w_wbs1_adr           ),
  .i_s1_int   (w_wbs1_int           )
);

wishbone_mem_interconnect wmi (
  .clk        (clk                  ),
  .rst        (r_rst                ),

  //master
  .i_m_we     (w_mem_we_o           ),
  .i_m_cyc    (w_mem_cyc_o          ),
  .i_m_stb    (w_mem_stb_o          ),
  .i_m_sel    (w_mem_sel_o          ),
  .o_m_ack    (w_mem_ack_i          ),
  .i_m_dat    (w_mem_dat_o          ),
  .o_m_dat    (w_mem_dat_i          ),
  .i_m_adr    (w_mem_adr_o          ),
  .o_m_int    (w_mem_int_i          ),

  //slave 0
  .o_s0_we    (w_sm0_i_wbs_we       ),
  .o_s0_cyc   (w_sm0_i_wbs_cyc      ),
  .o_s0_stb   (w_sm0_i_wbs_stb      ),
  .o_s0_sel   (w_sm0_i_wbs_sel      ),
  .i_s0_ack   (w_sm0_o_wbs_ack      ),
  .o_s0_dat   (w_sm0_i_wbs_dat      ),
  .i_s0_dat   (w_sm0_o_wbs_dat      ),
  .o_s0_adr   (w_sm0_i_wbs_adr      ),
  .i_s0_int   (w_sm0_o_wbs_int      )
);

arbiter_2_masters arb0 (
  .clk        (clk                  ),
  .rst        (r_rst                ),

  //masters
  .i_m1_we    (mem_o_we             ),
  .i_m1_stb   (mem_o_stb            ),
  .i_m1_cyc   (mem_o_cyc            ),
  .i_m1_sel   (mem_o_sel            ),
  .i_m1_dat   (mem_o_dat            ),
  .i_m1_adr   (mem_o_adr            ),
  .o_m1_dat   (mem_i_dat            ),
  .o_m1_ack   (mem_i_ack            ),
  .o_m1_int   (mem_i_int            ),


  .i_m0_we    (w_sm0_i_wbs_we       ),
  .i_m0_stb   (w_sm0_i_wbs_stb      ),
  .i_m0_cyc   (w_sm0_i_wbs_cyc      ),
  .i_m0_sel   (w_sm0_i_wbs_sel      ),
  .i_m0_dat   (w_sm0_i_wbs_dat      ),
  .i_m0_adr   (w_sm0_i_wbs_adr      ),
  .o_m0_dat   (w_sm0_o_wbs_dat      ),
  .o_m0_ack   (w_sm0_o_wbs_ack      ),
  .o_m0_int   (w_sm0_o_wbs_int      ),

  //slave
  .o_s_we     (w_arb0_i_wbs_we      ),
  .o_s_stb    (w_arb0_i_wbs_stb     ),
  .o_s_cyc    (w_arb0_i_wbs_cyc     ),
  .o_s_sel    (w_arb0_i_wbs_sel     ),
  .o_s_dat    (w_arb0_i_wbs_dat     ),
  .o_s_adr    (w_arb0_i_wbs_adr     ),
  .i_s_dat    (w_arb0_o_wbs_dat     ),
  .i_s_ack    (w_arb0_o_wbs_ack     ),
  .i_s_int    (w_arb0_o_wbs_int     )
);

wb_dionysus_sdram m0 (

  .clk                 (clk                 ),
  .rst                 (r_rst               ),

  .i_wbs_we            (w_arb0_i_wbs_we     ),
  .i_wbs_sel           (w_arb0_i_wbs_sel    ),
  .i_wbs_cyc           (w_arb0_i_wbs_cyc    ),
  .i_wbs_dat           (w_arb0_i_wbs_dat    ),
  .i_wbs_stb           (w_arb0_i_wbs_stb    ),
  .i_wbs_adr           (w_arb0_i_wbs_adr    ),
  .o_wbs_dat           (w_arb0_o_wbs_dat    ),
  .o_wbs_ack           (w_arb0_o_wbs_ack    ),
  .o_wbs_int           (w_arb0_o_wbs_int    ),

  .o_sdram_clk         (sdram_clk           ),
  .o_sdram_cke         (sdram_cke           ),
  .o_sdram_cs_n        (sdram_cs_n          ),
  .o_sdram_ras         (sdram_ras           ),
  .o_sdram_cas         (sdram_cas           ),
  .o_sdram_we          (sdram_we            ),

  .o_sdram_addr        (sdram_addr          ),
  .o_sdram_bank        (sdram_bank          ),
  .io_sdram_data       (sdram_data          ),
  .o_sdram_data_mask   (sdram_data_mask     ),
  .o_sdram_ready       (sdram_ready         )
);

mt48lc4m16
//#(
//  tdevice_TRCD = 10
//)
ram (
  .A11                 (sdram_addr[11]      ),
  .A10                 (sdram_addr[10]      ),
  .A9                  (sdram_addr[9]       ),
  .A8                  (sdram_addr[8]       ),
  .A7                  (sdram_addr[7]       ),
  .A6                  (sdram_addr[6]       ),
  .A5                  (sdram_addr[5]       ),
  .A4                  (sdram_addr[4]       ),
  .A3                  (sdram_addr[3]       ),
  .A2                  (sdram_addr[2]       ),
  .A1                  (sdram_addr[1]       ),
  .A0                  (sdram_addr[0]       ),

  .DQ15                (sdram_data[15]      ),
  .DQ14                (sdram_data[14]      ),
  .DQ13                (sdram_data[13]      ),
  .DQ12                (sdram_data[12]      ),
  .DQ11                (sdram_data[11]      ),
  .DQ10                (sdram_data[10]      ),
  .DQ9                 (sdram_data[9]       ),
  .DQ8                 (sdram_data[8]       ),
  .DQ7                 (sdram_data[7]       ),
  .DQ6                 (sdram_data[6]       ),
  .DQ5                 (sdram_data[5]       ),
  .DQ4                 (sdram_data[4]       ),
  .DQ3                 (sdram_data[3]       ),
  .DQ2                 (sdram_data[2]       ),
  .DQ1                 (sdram_data[1]       ),
  .DQ0                 (sdram_data[0]       ),

  .BA0                 (sdram_bank[0]       ),
  .BA1                 (sdram_bank[1]       ),
  .DQMH                (sdram_data_mask[1]  ),
  .DQML                (sdram_data_mask[0]  ),
  .CLK                 (sdram_clk           ),
  .CKE                 (sdram_cke           ),
  .WENeg               (sdram_we            ),
  .RASNeg              (sdram_ras           ),
  .CSNeg               (sdram_cs_n          ),
  .CASNeg              (sdram_cas           )
);

assign  w_wbs0_ack   = 0;
assign  w_wbs0_dat_o = 0;
assign  start = sdram_ready;

//Disable Slave 0
assign  w_wbs0_int              = 0;
assign  w_wbs0_ack              = 0;
assign  w_wbs0_dat_o            = 0;
assign  device_interrupt        = w_wbp_int;


//  READ ME IF YOUR MODULE WILL INTERFACE WITH MEMORY
//
//  If you want to talk to memory over the wishbone bus directly, your module must control the following signals:
//
//  (Your module will be a wishbone master)
//    mem_o_we
//    mem_o_stb
//    mem_o_cyc
//    mem_o_sel
//    mem_o_adr
//    mem_o_dat
//    mem_i_dat
//    mem_i_ack
//    mem_i_int
//
//  Currently this bus is disabled so if will not interface with memory these signals can be left
//
//  For a reference check out wb_sd_host

assign  mem_o_we                = 0;
assign  mem_o_stb               = 0;
assign  mem_o_cyc               = 0;
assign  mem_o_sel               = 0;
assign  mem_o_adr               = 0;
assign  mem_o_dat               = 0;

//Submodules
//Asynchronous Logic
//Synchronous Logic
//Simulation Control
initial begin
  $dumpfile ("design.vcd");
  $dumpvars(0, tb_cocotb);
end



endmodule
