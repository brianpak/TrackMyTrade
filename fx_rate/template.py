import os, datetime, calendar

def main():
    month1 = input("Enter month: ")
    month2 = input("Confirm month: ")

    if month1 != month2:
        sys.exit('Enter correct month.')
    
    month = int(month1)
    _, year_dir = os.path.split(os.getcwd())
    year = int(year_dir)
    
    filename = f'{month}.csv'
    with open(filename, mode='w') as f:
        f.write('Day,Rate' + '\n')

        _, num_days = calendar.monthrange(year, month)
        
        for i in range(1, num_days + 1):
            date = datetime.date(year, month, i)
            
            if date.weekday() < 5: # 0: Monday ... 6: Sunday
                f.write(f'{i},')

                if i != num_days:
                    f.write('\n')

if __name__ == "__main__":
    main()