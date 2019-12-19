#!/usr/bin/python

# TODO(dmw) update docstring + update to py3
"""
Input Options
- put up cash to exercise or sell enough to exercise
- % of exercised options, 20 - 100 % in increments of 10%

Output
- resulting income, regular and amt-only

Probably best as a stacked-bar 3d graph:
- (z-axis) front row sells to exercise and back row puts up cash
- (x-axis) % of options exercised
- (y-axis) income color coded for regular or amt-only

later add arguments for all constants and bool for whether to print
a table versus open gnuplot and feed it config
"""

import argparse
import prettytable
import subprocess
import sys
import tempfile

# easy to imagine 0 and break-even pay-off for all shares purchased
# but give three cumulative offsets for low/med/high price at future sale
# translates to break-even +$5, then +$15 and then +$30
guess_low = 5.0
guess_med = 10.0
guess_high = 15.0

percent_step = 10
max_percent = 100

# not dealing with infinite income
MAX = 100000000

# TODO(dmw) add option to singles

# 2019 married federal income tax rates
# amounts are the delta between the brackets
tax_rates = [(.10, 19400),
             (.12, 59550),
             (.22, 89450),
             (.24, 153050),
             (.32, 86750),
             (.35, 204150),
             (.37, MAX)]
# married standard deduction
standard_deduction = 24400

# 2019 married AMT rates
# TODO(dmw) AMT phaseout is not handled, starts > $1M for married couples
amt_low_rate = .26
amt_high_rate = .28
# after amt exception is subtracted (194800 - 111700)
amt_rate_cutoff = 83100

# 2019 married AMT exemption
amt_exemption = 111700

# MUST use double quotes in all gnuplot commands
gnuplot_cmd_block = '''set datafile separator " "
set terminal wxt enhanced font "Ariel,8" persist
set border 3 front lt black linewidth 1.000 dashtype solid
set grid y
set format y "%.1s%c"
set ylabel "Dollars"
set xlabel "ISO % Exercised"
set xlabel  offset character 0, -1, 0 font "Ariel,8" textcolor lt -1 norotate
set autoscale
set style data histograms
set style histogram clustered gap 1 title textcolor lt -1 offset character 2, -0.15
set style histogram rowstacked title offset 0,1
set style fill solid noborder
set boxwidth 0.95
set xtics border in scale 0,0 nomirror rotate by -45  autojustify
set xtics norangelimit  font ",7"
set xtics ()
set ytics border in scale 0,0 mirror norotate  autojustify
set ytics norangelimit autofreq  font ",8"
set ztics border in scale 0,0 nomirror norotate  autojustify
set cbtics border in scale 0,0 mirror norotate  autojustify
set rtics axis in scale 0,0 nomirror norotate  autojustify
set key bmargin center horizontal Left reverse noenhanced autotitle nobox
plot newhistogram "Taxable Income", "{}" using 2:xticlabels(1) t "Freed Income" linecolor rgb "#488f31", "" using 3 t "Spent Income" linecolor rgb "#f6bc63", "" using 4 t "AMT Income" linecolor rgb "#f19452", newhistogram "Regular Tax Estimate", "" using 5:xticlabels(1) t "Income Tax Est." linecolor rgb "#e66a4d", newhistogram "AMT Estimate", "" using 6:xticlabels(1) t "AMT Est." linecolor rgb "#de425b", newhistogram "Guess Future Returns", "" using 7:xticlabel(1) t "Share price break-even" linecolor rgb "#f7e382", "" using 8 t "Share price low" linecolor rgb "#bdcf75", "" using 9 t "Share price med" linecolor rgb "#85b96f", "" using 10 t "Share price high" linecolor rgb "#4fa16e" '''

tax_table_columns = (
    "Percent Exercised",
    "Sold Shares",
    "Sale Income",
    "Spent Sale Income",
    "Shares Held",
    "AMT Income",
    "Tax Estimate",
    "AMT Estimate",
)

guess_table_columns = (
    "Percent Exercised",
    "Shares Held",
    "Break-even Amount",
    "Break-even PPS",
    "Guess Low Amount",
    "Guess Low PPS",
    "Guess Med Amount",
    "Guess Med PPS",
    "Guess High Amount",
    "Guess High PPS",
)


def get_income_tax(income):
    total_tax = 0
    x = income
    for rate, cap in tax_rates:
        if x <= 0:
            break
        elif x > cap:
            total_tax += cap * rate
            x = x - cap
        else:
            total_tax += x * rate
            x = x - cap
    return total_tax


def get_amt(income):
    rate = amt_low_rate
    if income > amt_rate_cutoff:
        rate = amt_high_rate
    return income * rate


def run_gnuplot(datafile):
    gnuplot_cmds = ["gnuplot", "-p", "-e", "'"]
    for line in gnuplot_cmd_block.splitlines():
        gnuplot_cmds.append('{};'.format(line))
    gnuplot_cmds.append("'")
    cmd = " ".join(gnuplot_cmds).format(datafile)
    print "Running gnuplot with args: %s" % cmd
    popen = subprocess.Popen(cmd.format(datafile), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    out, err = popen.communicate()
    print "gnuplot output: %s" % out
    print "gnuplot err: %s" % err


def main(args):
    # TODO(dmw) hollow this out, create object to output different csv row types cast appropriately
    shares = args.shares[0]
    otherincome = float(args.otherincome[0])
    sell = args.sell[0]
    currentprice = args.currentprice[0]
    strikeprice = args.strikeprice[0]
    fmvprice = args.fmvprice[0]
    data = []
    tax_table = prettytable.PrettyTable(field_names=tax_table_columns)
    guess_table = prettytable.PrettyTable(field_names=guess_table_columns)
    for exercise_pct in range(sell, max_percent + 1, percent_step):
        # always start with upfront sale of all allowed
        # DO NOT INCLUDE COST TO BUY FIRST 20% -- IT IS NOT TAXABLE INCOME
        sold_shares = shares * sell / max_percent
        free_income = sold_shares * (currentprice - strikeprice)
        # shares exercised beyond the 20%
        exercised_shares = float(exercise_pct - sell) / max_percent * shares
        spent_income =  exercised_shares * strikeprice
        if spent_income > 0:
            free_income -= spent_income
        # AMT does not apply to first 20% which is regular income instead
        amt_income = exercised_shares * (fmvprice - strikeprice)

        # print 'total: %s free: %s spent: %s other: %s std: %s' % (free_income + spent_income + otherincome - standard_deduction, free_income, spent_income, otherincome, standard_deduction)
        est_tax = get_income_tax(free_income + spent_income + otherincome - standard_deduction)
        # print 'percent %s got %s est tax' % (exercise_pct, est_tax)
        est_amt_tax = get_amt(free_income + spent_income + amt_income + otherincome - amt_exemption)

        # calculate break-even point (for later when a sale is possible) what does that price look like?
        # (total) not per share since that won't graph well w/ a large y-axis
        # includes:
        # - NOT INCLUDED - cost to exercise original percent sold (TODO: not great for 20% case, already re-couped and sold)
        # - original sale proceeds used to exercise additional shares (30% and up)
        # - difference between AMT and regular income tax (if AMT is higher, otherwise 0)
        if not exercised_shares:
            shares_price_neutral = 0
        else:
            amt = est_amt_tax - est_tax if est_amt_tax > est_tax else 0
            shares_price_neutral = (spent_income + amt) / exercised_shares

        guess_neutral = shares_price_neutral * exercised_shares
        guess_price_low = guess_low * exercised_shares
        guess_price_med = guess_med * exercised_shares
        guess_price_high = guess_high * exercised_shares

        data_str = " ".join(['{}%'.format(exercise_pct), str(free_income), str(spent_income), str(amt_income), str(est_tax), str(est_amt_tax), str(guess_neutral), str(guess_price_low), str(guess_price_med), str(guess_price_high)])
        # print data_str.__repr__()
        data.append(data_str)
        tax_table.add_row(
            ('{}%'.format(exercise_pct),
             sold_shares,
             round(free_income + spent_income, 2),
             round(spent_income, 2),
             exercised_shares,
             round(amt_income, 2),
             round(est_tax, 2),
             round(est_amt_tax, 2))
        )
        guess_table.add_row(
            ('{}%'.format(exercise_pct),
             exercised_shares,
             round(guess_neutral, 2),
             round(shares_price_neutral, 2),
             round(guess_price_low + guess_neutral, 2),
             round(shares_price_neutral + guess_low, 2),
             round(guess_price_med + guess_price_low + guess_neutral, 2),
             round(shares_price_neutral + guess_low + guess_med, 2),
             round(guess_price_high + guess_price_med + guess_price_low + guess_neutral, 2),
             round(shares_price_neutral + guess_low + guess_med + guess_high, 2))
        )

    # TODO(dmw) figure out better way than leaving trash in /tmp
    with tempfile.NamedTemporaryFile(delete=False) as fp:
        fp.write("\n".join(data))
    run_gnuplot(fp.name)
    print "Tax Table"
    print tax_table.get_string()
    print
    print "Guess-the-Future Table"
    print guess_table.get_string()


if __name__ == "__main__":
    parser = argparse.ArgumentParser("pyamt.py")
    parser.add_argument('--sell', nargs=1, default=[20], type=int, help='Percentage to sell to fund acquiring more shares (must be enough currently)')
    parser.add_argument('--shares', nargs=1, default=[40000], type=int, help='Total number of shares')
    parser.add_argument('--strikeprice', nargs=1, default=[1.00], type=float, help='Strike price per share')
    parser.add_argument('--currentprice', nargs=1, default=[15.0], type=float, help='Current market price per share')
    parser.add_argument('--fmvprice', nargs=1, default=[10.0], type=float, help='Current Fair Market Value (FMV) per share')
    parser.add_argument('--otherincome', nargs=1, default=[80000], type=int, help='Other income in exercise year -- used to calculate estimated taxes')
    args = parser.parse_args(sys.argv[1:])

    main(args)
