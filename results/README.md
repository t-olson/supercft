# results
This folder should store the figures and lists generated by the scripts. Be careful about overwriting others' work

Desired format:
filename.pdf
`TODO.txt` # How should we output the files?

Use variations on the following code to generate figures:
```
import matplotlib
matplotlib.use('pdf')
import matplotlib.pyplot as plt # must come after .use()
fig = plt.figure()
plt.scatter(dictionary_of_points.keys(), dictionary_of_points.values())
fig.savefig(results_path + 'filename.pdf', bbox_inches='tight')
```


